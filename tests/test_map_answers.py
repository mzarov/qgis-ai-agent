import os
import tempfile
import unittest

from qgis.core import QgsVectorLayer

from qgis_ai_agent.qgis_tools.inspect import select_features as select_module
from qgis_ai_agent.qgis_tools.inspect.select_features import SelectFeaturesTool
from qgis_ai_agent.qgis_tools.project import export_layer as export_module
from qgis_ai_agent.qgis_tools.project.export_layer import FORMATS, ExportLayerTool, _checked_path, _suffix
from qgis_ai_agent.ui import welcome


class SelectableLayer(QgsVectorLayer):
    def __init__(self, matched=3):
        self.expressions = []
        self._matched = matched

    def name(self):
        return "Дороги"

    def selectByExpression(self, expression):
        self.expressions.append(expression)

    def selectedFeatureCount(self):
        return self._matched

    def selectedFeatureIds(self):
        return list(range(self._matched))


class SelectFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.tool = SelectFeaturesTool()
        self.layer = SelectableLayer()
        self.saved_find = select_module.find_layer_by_name
        self.saved_compile = select_module.compile_expression
        select_module.find_layer_by_name = lambda name: self.layer
        select_module.compile_expression = lambda text, label, layer=None: None

    def tearDown(self):
        select_module.find_layer_by_name = self.saved_find
        select_module.compile_expression = self.saved_compile

    def test_selection_is_a_read_tool(self):
        self.assertTrue(self.tool.is_read_only)

    def test_a_missing_filter_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"layer_name": "Дороги", "filter": "  "})
        self.assertIn("filter is required", str(caught.exception))

    def test_matching_features_are_selected_and_counted(self):
        result = self.tool.execute({"layer_name": "Дороги", "filter": "highway = 'motorway'"})
        self.assertEqual(result["selected"], 3)
        self.assertEqual(self.layer.expressions, ["highway = 'motorway'"])

    def test_an_empty_match_says_so_instead_of_pretending(self):
        self.layer._matched = 0
        result = self.tool.execute({"layer_name": "Дороги", "filter": "highway = 'nope'"})
        self.assertEqual(result["selected"], 0)
        self.assertIn("Nothing matches", result["note"])

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())


class ExportPathTest(unittest.TestCase):
    def test_every_known_extension_maps_to_a_driver(self):
        for suffix, driver in FORMATS.items():
            self.assertTrue(driver)
            self.assertTrue(suffix.startswith("."))

    def test_an_unknown_extension_lists_the_supported_ones(self):
        with self.assertRaises(ValueError) as caught:
            _checked_path("/tmp/data.kml")
        self.assertIn(".geojson", str(caught.exception))

    def test_a_missing_folder_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_path("/no/such/folder/data.gpkg")
        self.assertIn("does not exist", str(caught.exception))

    def test_the_suffix_is_read_case_insensitively(self):
        self.assertEqual(_suffix("/tmp/DATA.GeoJSON"), ".geojson")

    def test_a_valid_path_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "out.gpkg")
            self.assertEqual(_checked_path(path), path)


class ExportLayerTest(unittest.TestCase):
    def setUp(self):
        self.tool = ExportLayerTool()
        self.layer = SelectableLayer(matched=0)
        self.saved = export_module._require_vector
        export_module._require_vector = lambda name: self.layer

    def tearDown(self):
        export_module._require_vector = self.saved

    def test_selected_only_without_a_selection_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError) as caught:
            self.tool.prepare(
                {
                    "layer_name": "Дороги",
                    "path": os.path.join(folder, "out.gpkg"),
                    "selected_only": True,
                }
            )
        self.assertIn("Nothing is selected", str(caught.exception))

    def test_a_bad_crs_is_refused_before_writing(self):
        class Invalid:
            def __init__(self, text):
                self.text = text

            def isValid(self):
                return False

        saved = export_module.QgsCoordinateReferenceSystem
        export_module.QgsCoordinateReferenceSystem = Invalid
        try:
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError) as caught:
                self.tool.prepare(
                    {"layer_name": "Дороги", "path": os.path.join(folder, "out.gpkg"), "crs": "нет такой"}
                )
        finally:
            export_module.QgsCoordinateReferenceSystem = saved
        self.assertIn("coordinate system", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())


class WelcomeTest(unittest.TestCase):
    def test_a_configured_plugin_offers_examples(self):
        title, _, suggestions = welcome.welcome_content(True)
        self.assertEqual(title, welcome.READY_TITLE)
        self.assertEqual(suggestions, welcome.SUGGESTIONS)

    def test_an_unconfigured_plugin_points_at_the_settings_instead(self):
        title, _, suggestions = welcome.welcome_content(False)
        self.assertEqual(title, welcome.NEEDS_KEY_TITLE)
        self.assertEqual(suggestions, ())

    def test_the_examples_are_real_requests_not_placeholders(self):
        for text in welcome.SUGGESTIONS:
            self.assertGreater(len(text), 20)
            self.assertNotIn("TODO", text)

    def test_the_unconfigured_copy_explains_the_local_option(self):
        self.assertIn("localhost", welcome.NEEDS_KEY_BODY)


if __name__ == "__main__":
    unittest.main()
