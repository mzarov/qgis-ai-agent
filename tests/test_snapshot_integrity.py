import os
import tempfile
import unittest
from pathlib import Path

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.common.project_identity import project_identity
from qgis_ai_agent.qgis_tools.project import snapshots
from qgis_ai_agent.qgis_tools.project import undo_last_apply as undo_module
from qgis_ai_agent.qgis_tools.project.undo_last_apply import UndoLastApplyTool


class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        for slot in self._slots:
            slot()


class StatefulProject:
    def __init__(self, file_name: str, preset_home: str = "", dirty: bool = True):
        self._file_name = file_name
        self._preset_home = preset_home
        self._dirty = dirty
        self.write_ok = True
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

    def write(self, path):
        self._file_name = path
        self._dirty = False
        Path(path).touch()
        return self.write_ok

    def read(self, path):
        self.read_calls.append(path)
        self.cleared.emit()
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

    def tearDown(self):
        snapshots.QgsProject, undo_module.QgsProject, snapshots.snapshot_folder = self.saved
        snapshots._LAST.clear()
        snapshots._STATES.clear()
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


if __name__ == "__main__":
    unittest.main()
