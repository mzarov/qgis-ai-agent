import itertools
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.common.project_identity import project_identity, remember_save_as, same_project
from ai_agent.qgis_tools.project import restore as undo_module
from ai_agent.qgis_tools.project import scratch_copies, snapshots
from ai_agent.qgis_tools.project.remove_layer import RemoveLayerTool
from ai_agent.qgis_tools.project.undo_last_apply import UndoLastApplyTool


def raising(error):
    def fail(*args):
        raise error

    return fail


class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        for slot in self._slots:
            slot()


class NamedField:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class RecordedFeature:
    def __init__(self, fields=None, attributes=(), geometry=None, fid=0):
        self.fields = fields
        self._attributes = list(attributes)
        self._geometry = geometry
        self._id = fid

    def id(self):
        return self._id

    def setId(self, fid):
        self._id = fid

    def attributes(self):
        return list(self._attributes)

    def setAttributes(self, values):
        self._attributes = list(values)

    def hasGeometry(self):
        return self._geometry is not None

    def geometry(self):
        return self._geometry

    def setGeometry(self, geometry):
        self._geometry = geometry


class MemoryProvider:
    def __init__(self, field_names, features):
        self._fields = [NamedField(name) for name in field_names]
        self.features = list(features)
        self.next_id = 1

    def fields(self):
        return list(self._fields)

    def getFeatures(self):
        return iter(list(self.features))

    def subsetString(self):
        return ""

    def featureCount(self):
        return len(self.features)

    def addFeatures(self, features):
        for feature in features:
            feature.setId(self.next_id)
            self.next_id += 1
        self.features.extend(features)
        return True, features

    def deleteFeatures(self, ids):
        self.features = [feature for feature in self.features if feature.id() not in set(ids)]
        return True


class MemoryLayer:
    def __init__(self, name, field_names, features, provider_type="memory"):
        self._name = name
        self._provider_type = provider_type
        self.provider = MemoryProvider(field_names, features)
        self.repaints = 0

    def id(self):
        return f"{self._name}_id"

    def name(self):
        return self._name

    def providerType(self):
        return self._provider_type

    def isEditable(self):
        return False

    def featureCount(self):
        return len(self.provider.features)

    def dataProvider(self):
        return self.provider

    def updateExtents(self):
        pass

    def triggerRepaint(self):
        self.repaints += 1


class StatefulProject:
    def __init__(self, file_name: str, preset_home: str = "", dirty: bool = True):
        self._file_name = file_name
        self._preset_home = preset_home
        self._dirty = dirty
        self.write_ok = True
        self.writes = 0
        self.foreign_writes = 0
        self.read_ok = True
        self.read_failure = None
        self.read_calls = []
        self.cleared = Signal()
        self.layers = []

    def fileName(self):
        return self._file_name

    def setFileName(self, value):
        self._file_name = value

    def presetHomePath(self):
        return self._preset_home

    def setPresetHomePath(self, value):
        self._preset_home = value

    def homePath(self):
        return self._preset_home or os.path.dirname(self._file_name)

    def isDirty(self):
        return self._dirty

    def setDirty(self, value):
        self._dirty = bool(value)

    def mapLayers(self):
        return {str(index): layer for index, layer in enumerate(self.layers)}

    def mapLayer(self, layer_id):
        return next((layer for layer in self.layers if layer.id() == layer_id), None)

    def write(self, path):
        self._file_name = path
        self._dirty = False
        self.writes += 1
        inner = "another_project" if self.writes <= self.foreign_writes else Path(path).name.split(".", 1)[0]
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"{inner}.qgs", "<qgis/>")
        return self.write_ok

    def read(self, path):
        self.read_calls.append(path)
        self.cleared.emit()
        for layer in self.layers:
            if isinstance(layer, MemoryLayer) and layer.providerType() == "memory":
                layer.provider.features = []
                layer.provider.next_id = 1
        self._file_name = path
        self._dirty = False
        if self.read_failure is not None:
            raise self.read_failure
        return self.read_ok


class SnapshotIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.project = StatefulProject(
            os.path.join(self.folder.name, "live.qgz"),
            os.path.join(self.folder.name, "project-home"),
            dirty=True,
        )
        holder = type("ProjectHolder", (), {"instance": staticmethod(lambda: self.project)})
        self.saved = (snapshots.QgsProject, undo_module.QgsProject, snapshots.snapshot_folder)
        snapshots.QgsProject = holder
        undo_module.QgsProject = holder
        snapshots.snapshot_folder = lambda: self.folder.name
        snapshots._LAST.clear()
        snapshots._STATES.clear()
        snapshots._SCRATCH.clear()

    def tearDown(self):
        snapshots.QgsProject, undo_module.QgsProject, snapshots.snapshot_folder = self.saved
        snapshots._LAST.clear()
        snapshots._STATES.clear()
        snapshots._SCRATCH.clear()
        self.folder.cleanup()

    def test_snapshot_preserves_live_filename_home_and_dirty_state(self):
        original = (self.project.fileName(), self.project.homePath(), self.project.isDirty())

        path = snapshots.take_snapshot()

        self.assertTrue(os.path.isfile(path))
        self.assertEqual((self.project.fileName(), self.project.homePath(), self.project.isDirty()), original)

    def test_failed_snapshot_still_restores_live_project_identity(self):
        original = (self.project.fileName(), self.project.homePath(), self.project.isDirty())
        self.project.write_ok = False

        self.assertEqual(snapshots.take_snapshot(), "")

        self.assertEqual((self.project.fileName(), self.project.homePath(), self.project.isDirty()), original)
        self.assertEqual(snapshots.last_snapshot(), "")
        self.assertEqual(list(Path(self.folder.name).glob("before_apply_*.qgz")), [])

    def test_a_snapshot_another_qgis_overwrote_is_written_again(self):
        self.project.foreign_writes = 1

        path = snapshots.take_snapshot()

        self.assertEqual(self.project.writes, 2)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), [f"{Path(path).name.split('.', 1)[0]}.qgs"])

    def test_a_snapshot_that_keeps_coming_out_foreign_is_refused(self):
        self.project.foreign_writes = snapshots.MAX_WRITE_ATTEMPTS

        self.assertEqual(snapshots.take_snapshot(), "")

        self.assertEqual(self.project.writes, snapshots.MAX_WRITE_ATTEMPTS)
        self.assertEqual(list(Path(self.folder.name).glob("before_apply_*.qgz")), [])

    def test_snapshot_refuses_to_ignore_an_active_edit_buffer(self):
        layer = type(
            "EditingLayer",
            (),
            {"isEditable": staticmethod(lambda: True), "name": staticmethod(lambda: "manual edits")},
        )()
        self.project.layers = [layer]
        self.assertEqual(snapshots.take_snapshot(), "")
        self.assertIn("manual edits", snapshots.snapshot_error())
        self.assertEqual(list(Path(self.folder.name).glob("before_apply_*.qgz")), [])

    def test_undo_loads_snapshot_but_keeps_real_filename_and_marks_dirty(self):
        original_name = self.project.fileName()
        original_home = self.project.homePath()
        path = snapshots.take_snapshot()

        result = UndoLastApplyTool().execute({})

        self.assertEqual(result["restored_from"], path)
        self.assertEqual(self.project.read_calls, [path])
        self.assertEqual(self.project.fileName(), original_name)
        self.assertEqual(self.project.homePath(), original_home)
        self.assertTrue(self.project.isDirty())
        self.assertEqual(snapshots.last_snapshot(), "")
        self.assertFalse(os.path.exists(path))

    def test_confirming_undo_uses_the_snapshot_pinned_when_it_was_queued(self):
        prior = snapshots.take_snapshot()
        prepared = UndoLastApplyTool().prepare({})
        loop = AgentLoop()
        loop._batch._calls = [ToolCall(id="undo-1", name="undo_last_apply", arguments=prepared)]

        loop.confirm_pending()

        self.assertEqual(self.project.read_calls, [prior])
        self.assertEqual(snapshots.last_snapshot(), "")

    def test_two_confirmed_undos_walk_back_two_snapshots_in_order(self):
        first = snapshots.take_snapshot()
        second = snapshots.take_snapshot()
        loop = AgentLoop()
        for expected in (second, first):
            prepared = UndoLastApplyTool().prepare({})
            loop._batch._calls = [ToolCall(id=f"undo-{expected}", name="undo_last_apply", arguments=prepared)]
            loop.confirm_pending()
        self.assertEqual(self.project.read_calls, [second, first])
        self.assertEqual(snapshots.last_snapshot(), "")

    def test_undo_restores_the_same_unsaved_project_identity(self):
        self.project.setFileName("")
        original_identity = project_identity(self.project)
        path = snapshots.take_snapshot()

        result = UndoLastApplyTool().execute({})

        self.assertEqual(result["restored_from"], path)
        self.assertEqual(project_identity(self.project), original_identity)

    def test_undo_refuses_to_discard_an_active_edit_buffer(self):
        path = snapshots.take_snapshot()
        layer = type(
            "EditingLayer",
            (),
            {"isEditable": staticmethod(lambda: True), "name": staticmethod(lambda: "new manual edits")},
        )()
        self.project.layers = [layer]
        with self.assertRaisesRegex(ValueError, "Commit or roll back"):
            UndoLastApplyTool().execute({"_snapshot_path": path})
        self.assertEqual(self.project.read_calls, [])
        self.assertEqual(snapshots.last_snapshot(), path)

    def test_snapshot_from_another_unsaved_project_is_not_loaded(self):
        self.project.setFileName("")
        snapshots.take_snapshot()
        self.project.cleared.emit()

        with self.assertRaises(ValueError) as caught:
            UndoLastApplyTool().execute({})

        self.assertIn("another project", str(caught.exception))
        self.assertEqual(self.project.read_calls, [])

    def test_failed_undo_read_restores_pre_read_identity(self):
        snapshots.take_snapshot()
        original = (self.project.fileName(), self.project.homePath(), self.project.isDirty())
        self.project.read_ok = False

        with self.assertRaises(ValueError):
            UndoLastApplyTool().execute({})

        self.assertEqual((self.project.fileName(), self.project.homePath(), self.project.isDirty()), original)
        self.assertTrue(snapshots.last_snapshot())

    def test_undo_read_exception_restores_pre_read_identity(self):
        snapshots.take_snapshot()
        original = (self.project.fileName(), self.project.homePath(), self.project.isDirty())
        self.project.read_failure = RuntimeError("broken storage")

        with self.assertRaises(ValueError) as caught:
            UndoLastApplyTool().execute({})

        self.assertIn("broken storage", str(caught.exception))
        self.assertEqual((self.project.fileName(), self.project.homePath(), self.project.isDirty()), original)

    def test_snapshot_from_another_project_is_not_loaded(self):
        snapshots.take_snapshot()
        self.project.setFileName(os.path.join(self.folder.name, "other.qgz"))

        with self.assertRaises(ValueError) as caught:
            UndoLastApplyTool().execute({})

        self.assertIn("another project", str(caught.exception))
        self.assertEqual(self.project.read_calls, [])

    def test_a_snapshot_follows_its_project_saved_under_a_new_name(self):
        for first_name in (self.project.fileName(), ""):
            with self.subTest(first_name=first_name):
                self.project.setFileName(first_name)
                before = project_identity(self.project)
                path = snapshots.take_snapshot()
                copy = os.path.join(self.folder.name, "copy.qgz")
                self.project.setFileName(copy)
                snapshots.follow_project_move(before)

                result = UndoLastApplyTool().execute({})

                self.assertEqual(result["restored_from"], path)
                self.assertEqual(self.project.fileName(), copy, "Undo must not take the project back to its old file")
                self.assertTrue(self.project.isDirty())

    def test_undo_refills_memory_layers_the_project_file_cannot_hold(self):
        scratch = MemoryLayer(
            "buffers",
            ["name", "size"],
            [RecordedFeature(attributes=["a", 1], geometry="POINT(1 2)"), RecordedFeature(attributes=["b", 2])],
        )
        on_disk = MemoryLayer("roads", ["name"], [RecordedFeature(attributes=["main"])], provider_type="ogr")
        self.project.layers = [scratch, on_disk]
        snapshots.take_snapshot()
        scratch.provider._fields = [NamedField("size"), NamedField("name"), NamedField("extra")]

        with patch.object(scratch_copies, "QgsFeature", RecordedFeature):
            result = UndoLastApplyTool().execute({})

        self.assertEqual(
            [feature.attributes() for feature in scratch.provider.features], [[1, "a", None], [2, "b", None]]
        )
        self.assertEqual(scratch.provider.features[0].geometry(), "POINT(1 2)")
        self.assertFalse(scratch.provider.features[1].hasGeometry())
        self.assertEqual(scratch.repaints, 1)
        self.assertNotIn("empty_scratch_layers", result)

    def test_undo_gives_scratch_features_their_own_ids_back(self):
        scratch = MemoryLayer(
            "sparse", ["name"], [RecordedFeature(attributes=[name], fid=fid) for fid, name in ((1, "a"), (3, "c"))]
        )
        self.project.layers = [scratch]
        snapshots.take_snapshot()

        with patch.object(scratch_copies, "QgsFeature", RecordedFeature):
            result = UndoLastApplyTool().execute({})

        restored = [(feature.id(), feature.attributes()) for feature in scratch.provider.features]
        self.assertEqual(restored, [(1, ["a"]), (3, ["c"])], "a stand-in stayed or a feature took another id")
        self.assertEqual(scratch.provider.next_id, 4)
        self.assertNotIn("renumbered_scratch_layers", result)

    def test_undo_names_a_scratch_layer_with_too_many_missing_ids_to_keep(self):
        scratch = MemoryLayer(
            "sparse", ["name"], [RecordedFeature(attributes=[name], fid=fid) for fid, name in ((1, "a"), (4, "d"))]
        )
        self.project.layers = [scratch]
        with patch.object(scratch_copies, "MAX_STAND_INS", 1):
            snapshots.take_snapshot()

        with patch.object(scratch_copies, "QgsFeature", RecordedFeature):
            result = UndoLastApplyTool().execute({})

        self.assertEqual([feature.id() for feature in scratch.provider.features], [1, 2])
        self.assertEqual(result["renumbered_scratch_layers"], ["sparse"])
        self.assertIn("$id", result["renumbered_note"])

    def test_undo_names_scratch_layers_too_large_to_copy(self):
        scratch = MemoryLayer("huge", ["name"], [RecordedFeature(attributes=["a"])] * 3)
        self.project.layers = [scratch]
        with (
            patch.object(scratch_copies, "MAX_PRESERVED_FEATURES", 2),
            patch("ai_agent.qgis_tools.project.remove_layer.find_layer", lambda name: scratch),
            patch("ai_agent.qgis_tools.project.remove_layer.project", lambda: self.project),
        ):
            path = snapshots.take_snapshot()
            self.assertTrue(RemoveLayerTool().has_external_effect({"layer_name": "huge"}))

        self.assertIn("huge", UndoLastApplyTool().detail_call({"_snapshot_path": path}))
        result = UndoLastApplyTool().execute({})

        self.assertEqual(result["empty_scratch_layers"], ["huge"])
        self.assertIn("export_layer", result["scratch_note"])

    def test_removing_a_small_scratch_layer_stays_restorable(self):
        self.project.layers = [MemoryLayer("small", ["name"], [RecordedFeature(attributes=["a"])])]
        with (
            patch("ai_agent.qgis_tools.project.remove_layer.find_layer", lambda name: self.project.layers[0]),
            patch("ai_agent.qgis_tools.project.remove_layer.project", lambda: self.project),
        ):
            self.assertFalse(RemoveLayerTool().has_external_effect({"layer_name": "small"}))

    def test_the_feature_budget_is_shared_by_all_scratch_layers(self):
        first = MemoryLayer("first", ["name"], [RecordedFeature(attributes=["a"])] * 2)
        second = MemoryLayer("second", ["name"], [RecordedFeature(attributes=["b"])] * 2)
        self.project.layers = [first, second]
        with patch.object(scratch_copies, "MAX_PRESERVED_FEATURES", 3):
            self.assertEqual(scratch_copies.scratch_layers_over_budget(self.project), {"second_id"})
            copies = scratch_copies.copy_scratch_layers(self.project)
        self.assertEqual([copy.name for copy in copies.layers], ["first"])
        self.assertEqual(copies.not_copied, ("second",))

    def test_a_layer_that_came_back_with_features_is_not_refilled_twice(self):
        scratch = MemoryLayer("kept", ["name"], [RecordedFeature(attributes=["a"])])
        self.project.layers = [scratch]
        copies = scratch_copies.copy_scratch_layers(self.project)
        self.assertEqual(scratch_copies.restore_scratch_layers(self.project, copies), [])
        self.assertEqual(len(scratch.provider.features), 1)

    def test_a_write_that_raises_leaves_no_file_and_says_why(self):
        original = (self.project.fileName(), self.project.homePath(), self.project.isDirty())

        def broken_write(path):
            Path(path).touch()
            self.project.setFileName(path)
            raise RuntimeError("disk full")

        self.project.write = broken_write
        self.assertEqual(snapshots.take_snapshot(), "")
        self.assertEqual(snapshots.snapshot_error(), "disk full")
        self.assertEqual(list(Path(self.folder.name).glob("before_apply_*.qgz")), [])
        self.assertEqual((self.project.fileName(), self.project.homePath(), self.project.isDirty()), original)
        self.assertEqual(snapshots.last_snapshot(), "")

    def test_an_error_without_words_is_named_by_its_kind_and_forgotten_next_time(self):
        self.project.write = raising(OSError())
        self.assertEqual(snapshots.take_snapshot(), "")
        self.assertEqual(snapshots.snapshot_error(), "OSError")
        del self.project.write
        self.assertTrue(snapshots.take_snapshot())
        self.assertEqual(snapshots.snapshot_error(), "")

    def test_only_the_latest_snapshots_are_kept(self):
        with patch.object(snapshots, "time", SimpleNamespace(time_ns=itertools.count(1).__next__)):
            paths = [snapshots.take_snapshot() for _ in range(snapshots.MAX_SNAPSHOTS + 1)]
        oldest, kept = paths[0], paths[1:]
        self.assertFalse(os.path.exists(oldest))
        self.assertFalse(snapshots.snapshot_exists(oldest))
        self.assertIsNone(snapshots.snapshot_state(oldest))
        self.assertTrue(all(snapshots.snapshot_exists(path) for path in kept))
        self.assertEqual(snapshots.last_snapshot(), kept[-1])

    def test_a_snapshot_deleted_behind_the_plugins_back_is_skipped(self):
        first = snapshots.take_snapshot()
        second = snapshots.take_snapshot()
        os.remove(second)
        self.assertFalse(snapshots.snapshot_exists(second))
        self.assertEqual(snapshots.last_snapshot(), first)
        snapshots.drop_snapshot(second)
        snapshots.drop_snapshot("/never/taken.qgz")
        self.assertEqual(snapshots._LAST, [first])

    def test_layers_that_cannot_answer_do_not_stop_the_edit_check(self):
        class Broken:
            def isEditable(self):
                raise RuntimeError("deleted C++ object")

        class EditingWithoutName:
            def isEditable(self):
                return True

            def name(self):
                raise RuntimeError("deleted C++ object")

        self.project.layers = [Broken()]
        snapshots.ensure_project_read_safe(self.project)
        self.project.layers = [Broken(), EditingWithoutName()]
        with self.assertRaisesRegex(ValueError, "active edit buffer on: Unnamed"):
            snapshots.ensure_project_read_safe(self.project)
        self.project.mapLayers = raising(RuntimeError("project closing"))
        snapshots.ensure_project_read_safe(self.project)

    def test_a_scratch_layer_that_cannot_be_read_comes_back_named_empty(self):
        scratch = MemoryLayer("buffers", ["name"], [RecordedFeature(attributes=["a"])])
        scratch.provider.getFeatures = raising(RuntimeError("provider gone"))
        self.project.layers = [scratch]
        path = snapshots.take_snapshot()
        self.assertIn("buffers", UndoLastApplyTool().detail_call({"_snapshot_path": path}))
        result = UndoLastApplyTool().execute({})
        self.assertEqual(result["empty_scratch_layers"], ["buffers"])

    def test_a_refill_the_provider_refuses_is_named(self):
        scratch = MemoryLayer("buffers", ["name"], [RecordedFeature(attributes=["a"])])
        self.project.layers = [scratch]
        snapshots.take_snapshot()
        scratch.provider.addFeatures = lambda features: (False, [])
        with patch.object(scratch_copies, "QgsFeature", RecordedFeature):
            result = UndoLastApplyTool().execute({})
        self.assertEqual(result["empty_scratch_layers"], ["buffers"])
        self.assertIn("could not be refilled", result["scratch_note"])
        self.assertEqual(scratch.repaints, 0)

    def test_stand_ins_the_provider_keeps_are_named(self):
        sparse = [RecordedFeature(attributes=[name], fid=fid) for fid, name in ((1, "a"), (3, "c"))]
        scratch = MemoryLayer("sparse", ["name"], sparse)
        self.project.layers = [scratch]
        snapshots.take_snapshot()
        scratch.provider.deleteFeatures = lambda ids: False
        with patch.object(scratch_copies, "QgsFeature", RecordedFeature):
            result = UndoLastApplyTool().execute({})
        self.assertEqual(result["empty_scratch_layers"], ["sparse"])
        self.assertNotIn("renumbered_scratch_layers", result)

    def test_a_project_that_cannot_list_its_layers_copies_nothing(self):
        self.project.mapLayers = raising(RuntimeError("project closing"))
        self.assertEqual(scratch_copies.copy_scratch_layers(self.project), scratch_copies.ScratchCopies())
        self.project.mapLayer = raising(RuntimeError("project closing"))
        copy = scratch_copies.ScratchLayerCopy("gone_id", "gone", ("name",), [RecordedFeature(attributes=["a"])])
        copies = scratch_copies.ScratchCopies((copy,))
        self.assertEqual(scratch_copies.restore_scratch_layers(self.project, copies), [])


class ProcessFolderTest(unittest.TestCase):
    def setUp(self):
        self.saved = snapshots._PROCESS_FOLDER
        self.addCleanup(setattr, snapshots, "_PROCESS_FOLDER", self.saved)

    def test_the_snapshot_folder_is_private_and_made_once(self):
        snapshots._PROCESS_FOLDER = ""
        folder = snapshots.snapshot_folder()
        self.addCleanup(os.rmdir, folder)
        self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
        self.assertEqual(snapshots.snapshot_folder(), folder)

    def test_quitting_removes_the_snapshots_and_only_them(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, "ai_agent_snapshots_x")
            os.mkdir(folder)
            snapshots._PROCESS_FOLDER = folder
            for name in ("before_apply_1.qgz", "before_apply_2.qgz", "notes.txt"):
                Path(folder, name).touch()
            snapshots._cleanup_process_folder()
            self.assertEqual(os.listdir(folder), ["notes.txt"])
            os.remove(os.path.join(folder, "notes.txt"))
            snapshots._cleanup_process_folder()
            self.assertFalse(os.path.exists(folder))
            snapshots._cleanup_process_folder()
        snapshots._PROCESS_FOLDER = ""
        snapshots._cleanup_process_folder()


class SaveAsIdentityTest(unittest.TestCase):
    def test_a_save_as_keeps_the_project_and_another_project_stays_another(self):
        remember_save_as("unsaved:save-as-test", "/maps/city.qgz")
        remember_save_as("/maps/city.qgz", "/maps/city-final.qgz")
        self.assertTrue(same_project("/maps/city-final.qgz", "unsaved:save-as-test"))
        self.assertTrue(same_project("/maps/city.qgz", "/maps/city.qgz"))
        self.assertFalse(same_project("/maps/other.qgz", "unsaved:save-as-test"))
        self.assertFalse(same_project("unsaved:save-as-test", "/maps/city.qgz"), "a Save As is not undone backwards")


if __name__ == "__main__":
    unittest.main()
