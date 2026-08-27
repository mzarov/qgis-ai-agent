import unittest

from qgis_ai_agent.qgis_tools.inspect import get_selection as selection_module
from qgis_ai_agent.qgis_tools.inspect.get_selection import GetSelectionTool
from qgis_ai_agent.qgis_tools.inspect.query_layer import _restrict_to_selection
from qgis_ai_agent.qgis_tools.project import add_basemap as basemap_module
from qgis_ai_agent.qgis_tools.project import list_db_connections as connections_module
from qgis_ai_agent.qgis_tools.project.add_basemap import AddBasemapTool, _resolved, _xyz_source
from qgis_ai_agent.qgis_tools.project.add_db_layer import AddDbLayerTool
from qgis_ai_agent.qgis_tools.project.list_db_connections import ListDbConnectionsTool, require_connection
from qgis_ai_agent.qgis_tools.project.list_db_tables import ListDbTablesTool


class BasemapTest(unittest.TestCase):
    def setUp(self):
        self.tool = AddBasemapTool()

    def test_unknown_preset_lists_the_available_ones(self):
        with self.assertRaises(ValueError) as caught:
            _resolved({"preset": "google"})
        self.assertIn("osm", str(caught.exception))

    def test_custom_url_must_carry_the_placeholders(self):
        with self.assertRaises(ValueError) as caught:
            _resolved({"url": "https://host/tiles.png"})
        self.assertIn("{z}", str(caught.exception))

    def test_preset_brings_title_and_attribution(self):
        title, url, attribution = _resolved({"preset": "osm"})
        self.assertEqual(title, "OpenStreetMap")
        self.assertIn("{z}", url)
        self.assertIn("OpenStreetMap", attribution)

    def test_neither_preset_nor_url_is_an_error(self):
        with self.assertRaises(ValueError):
            _resolved({})

    def test_the_source_string_is_fully_encoded(self):
        source = _xyz_source("https://host/{z}/{x}/{y}.png?key=a&b=c")
        self.assertIn("type=xyz&url=", source)
        self.assertNotIn("?key", source)
        self.assertNotIn("&b=c", source)

    def test_duplicate_name_is_rejected_at_prepare(self):
        saved = basemap_module.layer_names
        basemap_module.layer_names = lambda: ["OpenStreetMap"]
        try:
            with self.assertRaises(ValueError) as caught:
                self.tool.prepare({"preset": "osm"})
        finally:
            basemap_module.layer_names = saved
        self.assertIn("already in the project", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())
        self.assertIn("OpenStreetMap", self.tool.summarize_call({"preset": "osm"}))


class Connection:
    def __init__(self, tables=()):
        self._tables = list(tables)

    def tables(self):
        return self._tables

    def tableUri(self, schema, table):
        return f"uri://{schema}.{table}"


class DbToolsTest(unittest.TestCase):
    def setUp(self):
        self.saved = connections_module.db_connections
        connections_module.db_connections = lambda: {"prod": Connection()}

    def tearDown(self):
        connections_module.db_connections = self.saved

    def test_missing_connection_lists_the_known_ones(self):
        with self.assertRaises(ValueError) as caught:
            require_connection("dev")
        self.assertIn("'prod'", str(caught.exception))

    def test_listing_returns_the_names(self):
        result = ListDbConnectionsTool().execute({})
        self.assertEqual(result["connections"], ["prod"])

    def test_no_connections_yields_a_browser_hint(self):
        connections_module.db_connections = lambda: {}
        result = ListDbConnectionsTool().execute({})
        self.assertIn("Browser", result["note"])

    def test_summaries_never_raise(self):
        self.assertTrue(ListDbConnectionsTool().summarize_call({}).strip())
        self.assertTrue(ListDbTablesTool().summarize_call({}).strip())
        self.assertTrue(AddDbLayerTool().summarize_call({}).strip())


class RestrictToSelectionTest(unittest.TestCase):
    def test_empty_selection_is_a_clear_error(self):
        class Layer:
            def name(self):
                return "Дороги"

            def selectedFeatureIds(self):
                return []

        with self.assertRaises(ValueError) as caught:
            _restrict_to_selection(Layer(), object())
        self.assertIn("Nothing is selected", str(caught.exception))

    def test_ids_land_in_the_request(self):
        class Layer:
            def selectedFeatureIds(self):
                return [3, 7]

        class Request:
            def setFilterFids(self, ids):
                self.ids = list(ids)

        request = Request()
        _restrict_to_selection(Layer(), request)
        self.assertEqual(request.ids, [3, 7])


class Project:
    def __init__(self, layers):
        self._layers = layers

    def mapLayers(self):
        return {str(i): layer for i, layer in enumerate(self._layers)}


class SelectionLayer:
    def __init__(self, name, selected):
        self._name = name
        self._selected = selected

    def name(self):
        return self._name

    def selectedFeatureCount(self):
        return len(self._selected)

    def fields(self):
        class F:
            def names(self):
                return ["name"]

        return F()

    def selectedFeatures(self):
        return list(self._selected)


class GetSelectionTest(unittest.TestCase):
    def test_empty_selection_says_so(self):
        saved = selection_module.QgsProject
        selection_module.QgsProject = type("P", (), {"instance": staticmethod(lambda: Project([]))})
        try:
            result = GetSelectionTool().execute({})
        finally:
            selection_module.QgsProject = saved
        self.assertEqual(result["selected_total"], 0)
        self.assertIn("Nothing", result["note"])

    def test_selected_layers_are_listed_with_counts(self):
        class Feature(dict):
            pass

        saved_project = selection_module.QgsProject
        saved_count = selection_module.selected_count
        layer = SelectionLayer("Дороги", [Feature(name="a"), Feature(name="b")])
        selection_module.QgsProject = type("P", (), {"instance": staticmethod(lambda: Project([layer]))})
        selection_module.selected_count = lambda item: item.selectedFeatureCount()
        try:
            result = GetSelectionTool().execute({})
        finally:
            selection_module.QgsProject = saved_project
            selection_module.selected_count = saved_count
        self.assertEqual(result["selected_total"], 2)
        self.assertEqual(result["selections"][0]["layer"], "Дороги")
        self.assertIn("selected_only", result["note"])


if __name__ == "__main__":
    unittest.main()
