import os
import tempfile
import unittest
from unittest.mock import patch

from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.fields import manage_fields as fields_module
from ai_agent.qgis_tools.fields.manage_fields import AddFieldTool, DeleteFieldTool, RenameFieldTool
from ai_agent.qgis_tools.fields.schema import build_field, checked_new_name
from ai_agent.qgis_tools.project import snapshots
from ai_agent.qgis_tools.project import views as views_module
from ai_agent.qgis_tools.project.add_service_layer import AddServiceLayerTool, _checked_service, _checked_url
from ai_agent.qgis_tools.project.undo_last_apply import UndoLastApplyTool
from ai_agent.qgis_tools.style import raster
from ai_agent.qgis_tools.style.set_raster_style import SetRasterStyleTool


class Fields:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)

    def indexFromName(self, name):
        return self._names.index(name) if name in self._names else -1


class VectorLayer:
    def __init__(self, names=("name", "type")):
        self._fields = Fields(names)
        self.added = []
        self.renamed = []
        self.deleted = []
        self.expression_fields = []
        self.rolled_back = False
        self._commit_ok = True
        self.editing = False
        self.commit_calls = 0

    def name(self):
        return "Дороги"

    def fields(self):
        return self._fields

    def startEditing(self):
        self.editing = True
        return True

    def isEditable(self):
        return self.editing

    def addAttribute(self, field):
        self.added.append(field)
        return True

    def renameAttribute(self, index, new_name):
        self.renamed.append((index, new_name))
        return True

    def deleteAttribute(self, index):
        self.deleted.append(index)
        return True

    def addExpressionField(self, expression, field):
        self.expression_fields.append(expression)
        return len(self._fields.names()) + len(self.expression_fields) - 1

    def commitChanges(self):
        self.commit_calls += 1
        if self._commit_ok:
            self.editing = False
        return self._commit_ok

    def commitErrors(self):
        return ["source is read-only"]

    def rollBack(self):
        self.rolled_back = True
        self.editing = False
        return True


class FieldsTestBase(unittest.TestCase):
    def setUp(self):
        self.layer = VectorLayer()
        self.saved_require = fields_module.require_vector
        self.saved_compile = fields_module.compile_expression
        fields_module.require_vector = lambda name: self.layer
        fields_module.compile_expression = lambda text, label, layer=None: None

    def tearDown(self):
        fields_module.require_vector = self.saved_require
        fields_module.compile_expression = self.saved_compile


class AddFieldTest(FieldsTestBase):
    def setUp(self):
        super().setUp()
        self.tool = AddFieldTool()

    def test_duplicate_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "name": "name"})
        self.assertIn("already has a field", str(caught.exception))

    def test_unknown_type_lists_the_available(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "name": "new", "type": "blob"})
        self.assertIn("integer", str(caught.exception))

    def test_a_plain_field_is_added_to_the_schema(self):
        result = self.tool.execute({"layer_name": "Дороги", "name": "status", "type": "text"})
        self.assertFalse(result["virtual"])
        self.assertEqual(len(self.layer.added), 1)

    def test_an_expression_makes_it_virtual(self):
        result = self.tool.execute({"layer_name": "Дороги", "name": "area_ha", "expression": "$area / 10000"})
        self.assertTrue(result["virtual"])
        self.assertEqual(self.layer.expression_fields, ["$area / 10000"])
        self.assertIn("project", result["note"])

    def test_failed_commit_rolls_back(self):
        self.layer._commit_ok = False
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"layer_name": "Дороги", "name": "status"})
        self.assertTrue(self.layer.rolled_back)
        self.assertIn("read-only", str(caught.exception))

    def test_refused_plain_field_does_not_commit(self):
        with (
            patch.object(self.layer, "addAttribute", return_value=False),
            self.assertRaisesRegex(ValueError, "refused to add"),
        ):
            self.tool.execute({"layer_name": "Дороги", "name": "status"})
        self.assertTrue(self.layer.rolled_back)
        self.assertEqual(self.layer.commit_calls, 0)

    def test_refused_virtual_field_is_reported(self):
        with (
            patch.object(self.layer, "addExpressionField", return_value=-1),
            self.assertRaisesRegex(ValueError, "refused to add virtual field"),
        ):
            self.tool.execute({"layer_name": "Дороги", "name": "status", "expression": "1"})
        self.assertFalse(self.layer.editing)

    def test_field_creation_exception_closes_the_edit_session(self):
        with (
            patch.object(self.layer, "addAttribute", side_effect=RuntimeError("provider failure")),
            self.assertRaisesRegex(ValueError, "provider failure"),
        ):
            self.tool.execute({"layer_name": "Дороги", "name": "status"})
        self.assertTrue(self.layer.rolled_back)
        self.assertFalse(self.layer.editing)

    def test_summary_distinguishes_virtual(self):
        plain = self.tool.summarize_call({"name": "a", "layer_name": "Д"})
        virtual = self.tool.summarize_call({"name": "a", "layer_name": "Д", "expression": "1"})
        self.assertNotEqual(plain, virtual)
        self.assertTrue(self.tool.summarize_call({}).strip())

    def test_plain_fields_are_external_but_virtual_fields_are_project_only(self):
        self.assertTrue(self.tool.has_external_effect({"name": "status"}))
        self.assertFalse(self.tool.has_external_effect({"name": "area", "expression": "$area"}))


class RenameDeleteFieldTest(FieldsTestBase):
    def test_rename_requires_an_existing_field(self):
        with self.assertRaises(ValueError):
            RenameFieldTool().prepare({"layer_name": "Д", "name": "nope", "new_name": "x"})

    def test_rename_lands(self):
        result = RenameFieldTool().execute({"layer_name": "Д", "name": "name", "new_name": "title"})
        self.assertEqual(result["to"], "title")
        self.assertEqual(self.layer.renamed, [(0, "title")])

    def test_delete_is_destructive(self):
        self.assertEqual(DeleteFieldTool().safety, SAFETY_DESTRUCTIVE)
        self.assertTrue(DeleteFieldTool().external_effect)

    def test_the_last_field_cannot_be_deleted(self):
        self.layer._fields = Fields(["only"])
        with self.assertRaises(ValueError) as caught:
            DeleteFieldTool().prepare({"layer_name": "Д", "name": "only"})
        self.assertIn("only field", str(caught.exception))

    def test_delete_lands(self):
        DeleteFieldTool().execute({"layer_name": "Д", "name": "type"})
        self.assertEqual(self.layer.deleted, [1])

    def test_refused_rename_and_delete_never_commit(self):
        cases = [
            (RenameFieldTool(), "renameAttribute", {"layer_name": "Д", "name": "name", "new_name": "title"}),
            (DeleteFieldTool(), "deleteAttribute", {"layer_name": "Д", "name": "type"}),
        ]
        for tool, method, arguments in cases:
            with self.subTest(tool=tool.name), patch.object(self.layer, method, return_value=False):
                with self.assertRaisesRegex(ValueError, "QGIS refused"):
                    tool.execute(arguments)
                self.assertTrue(self.layer.rolled_back)
                self.assertFalse(self.layer.editing)
                self.assertEqual(self.layer.commit_calls, 0)

    def test_last_field_guard_is_rechecked_at_execution(self):
        self.layer._fields = Fields(["only"])
        with self.assertRaisesRegex(ValueError, "only field"):
            DeleteFieldTool().execute({"layer_name": "Д", "name": "only"})
        self.assertFalse(self.layer.editing)


class SchemaHelpersTest(unittest.TestCase):
    def test_empty_name_is_refused(self):
        with self.assertRaises(ValueError):
            checked_new_name(VectorLayer(), "  ")

    def test_overlong_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            checked_new_name(VectorLayer(), "x" * 200)
        self.assertIn("truncate", str(caught.exception))

    def test_every_type_builds(self):
        from ai_agent.qgis_tools.fields.schema import FIELD_TYPES

        for kind in FIELD_TYPES:
            self.assertIsNotNone(build_field("f", kind))


class RasterHelpersTest(unittest.TestCase):
    def test_unknown_interpolation_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            raster.checked_interpolation("smooth")
        self.assertIn("linear", str(caught.exception))

    def test_class_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            raster.checked_classes(1)
        with self.assertRaises(ValueError):
            raster.checked_classes(999)
        self.assertEqual(raster.checked_classes(None), raster.DEFAULT_CLASSES)

    def test_band_outside_the_raster_is_refused(self):
        class Layer:
            def bandCount(self):
                return 2

        with self.assertRaises(ValueError) as caught:
            raster.checked_band(Layer(), 5)
        self.assertIn("2 band", str(caught.exception))

    def test_no_data_values_must_be_numbers(self):
        class Layer:
            def bandCount(self):
                return 1

        with self.assertRaises(ValueError) as caught:
            raster.apply_no_data(Layer(), ["junk"])
        self.assertIn("not a number", str(caught.exception))

    def test_no_data_accepts_an_empty_list(self):
        self.assertEqual(raster.apply_no_data(None, None), [])


class RasterToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = SetRasterStyleTool()

    def test_unknown_mode_lists_the_available(self):
        from ai_agent.qgis_tools.style.set_raster_style import _checked_mode

        with self.assertRaises(ValueError) as caught:
            _checked_mode("rainbow")
        self.assertIn("hillshade", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())
        self.assertIn("hillshade", self.tool.summarize_call({"mode": "hillshade", "layer_name": "DEM"}))


class ServiceLayerTest(unittest.TestCase):
    def test_unknown_service_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_service("wcs")
        self.assertIn("wms", str(caught.exception))

    def test_url_must_be_http(self):
        with self.assertRaises(ValueError) as caught:
            _checked_url("ftp://host/wms")
        self.assertIn("http", str(caught.exception))

    def test_query_string_is_stripped(self):
        self.assertEqual(_checked_url("https://host/wms?service=WMS"), "https://host/wms")

    def test_published_layer_is_required(self):
        tool = AddServiceLayerTool()
        with self.assertRaises(ValueError) as caught:
            tool.prepare({"service": "wms", "url": "https://host/wms"})
        self.assertIn("publishes", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(AddServiceLayerTool().summarize_call({}).strip())


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        snapshots._LAST.clear()

    def tearDown(self):
        snapshots._LAST.clear()

    def test_no_snapshot_means_nothing_to_undo(self):
        self.assertEqual(snapshots.last_snapshot(), "")
        with self.assertRaises(ValueError) as caught:
            UndoLastApplyTool().prepare({})
        self.assertIn("no snapshot", str(caught.exception))

    def test_a_vanished_file_is_forgotten(self):
        snapshots._LAST.append("/no/such/snapshot.qgz")
        self.assertEqual(snapshots.last_snapshot(), "")

    def test_the_newest_snapshot_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            older = os.path.join(folder, "a.qgz")
            newer = os.path.join(folder, "b.qgz")
            for path in (older, newer):
                open(path, "w").close()
            snapshots._LAST.extend([older, newer])
            self.assertEqual(snapshots.last_snapshot(), newer)
            snapshots.drop_last()
            self.assertEqual(snapshots.last_snapshot(), older)

    def test_undo_is_destructive(self):
        self.assertEqual(UndoLastApplyTool().safety, SAFETY_DESTRUCTIVE)

    def test_the_scope_limit_is_stated_to_the_model(self):
        from ai_agent.qgis_tools.project.undo_last_apply import SCOPE_NOTE

        self.assertIn("NOT undone", SCOPE_NOTE)
        self.assertIn("cannot undo edits", UndoLastApplyTool().description)

    def test_summary_never_raises(self):
        self.assertTrue(UndoLastApplyTool().summarize_call({}).strip())


class ViewsTest(unittest.TestCase):
    def test_duplicate_bookmark_is_refused(self):
        saved = views_module._bookmark_names
        views_module._bookmark_names = lambda: ["centre"]
        try:
            with self.assertRaises(ValueError) as caught:
                views_module.SaveBookmarkTool().prepare({"name": "centre"})
        finally:
            views_module._bookmark_names = saved
        self.assertIn("already exists", str(caught.exception))

    def test_duplicate_theme_is_refused(self):
        saved = views_module.project_themes
        views_module.project_themes = lambda: ["print"]
        try:
            with self.assertRaises(ValueError):
                views_module.SaveMapThemeTool().prepare({"name": "print"})
        finally:
            views_module.project_themes = saved

    def test_empty_names_are_refused(self):
        with self.assertRaises(ValueError):
            views_module.SaveBookmarkTool().prepare({"name": "  "})
        with self.assertRaises(ValueError):
            views_module.SaveMapThemeTool().prepare({"name": ""})

    def test_summaries_never_raise(self):
        for tool in (views_module.ListViewsTool(), views_module.SaveBookmarkTool(), views_module.SaveMapThemeTool()):
            self.assertTrue(tool.summarize_call({}).strip())


if __name__ == "__main__":
    unittest.main()
