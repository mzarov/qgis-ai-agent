import tempfile
import unittest
from unittest import mock

from ai_agent.qgis_tools.common.properties import properties_of
from ai_agent.qgis_tools.project import add_basemap, add_db_layer, add_service_layer, configure_layer, export_layer
from ai_agent.qgis_tools.project.add_layer import AddLayerTool


class Uri:
    def __init__(self, text=""):
        self.text = text
        self.params = {}

    def setGeometryColumn(self, column):
        self.params["geometry"] = column

    def setParam(self, key, value):
        self.params[key] = value

    def uri(self, expand):
        return " ".join([self.text, *(f"{key}='{value}'" for key, value in self.params.items())]).strip()


class Connection:
    def __init__(self, column):
        self._column = column

    def tableUri(self, schema, table):
        return f'table="{schema}"."{table}"'

    def table(self, schema, table):
        if self._column is None:
            raise RuntimeError("no such table")
        return type("Table", (), {"geometryColumn": lambda _self: self._column})()


class DatabaseTableTest(unittest.TestCase):
    def test_the_geometry_column_is_named_so_the_table_loads_with_geometry(self):
        with mock.patch.object(add_db_layer, "QgsDataSourceUri", Uri):
            self.assertIn("geometry='geom'", add_db_layer._table_uri(Connection("geom"), "public", "roads"))
            self.assertNotIn("geometry", add_db_layer._table_uri(Connection(""), "public", "notes"))
            self.assertNotIn("geometry", add_db_layer._table_uri(Connection(None), "public", "missing"))


class ServiceSourceTest(unittest.TestCase):
    def _built(self, service, url, published):
        opened = []
        with (
            mock.patch.object(add_service_layer, "QgsDataSourceUri", Uri),
            mock.patch.object(add_service_layer, "QgsVectorLayer", lambda source, *rest: opened.append(source)),
            mock.patch.object(add_service_layer, "QgsRasterLayer", lambda source, *rest: opened.append(source)),
        ):
            add_service_layer._built(service, url, published, "title", "EPSG:3857")
        return opened[0]

    def test_a_namespaced_typename_reaches_qgis_as_it_is_published(self):
        source = self._built("wfs", "https://host/ows", "ns:districts")
        self.assertIn("typename='ns:districts'", source)
        self.assertIn("url='https://host/ows'", source)

    def test_a_space_in_a_wms_layer_name_is_not_turned_into_a_plus(self):
        source = self._built("wms", "https://host/ows", "Topo Base")
        self.assertIn("layers=Topo%20Base", source)

    def test_the_endpoint_keeps_what_is_not_a_request_parameter(self):
        url = add_service_layer._checked_url("https://host/cgi-bin/mapserv?map=/data/city.map&SERVICE=WMS&request=x")
        self.assertEqual(url, "https://host/cgi-bin/mapserv?map=/data/city.map")


class RemoteSourceTest(unittest.TestCase):
    def test_a_source_gdal_fetches_is_marked_as_network_access(self):
        tool = AddLayerTool()
        for source in ("http://host/x.geojson", "HTTPS://host/x.tif", "/vsizip//vsicurl/https://host/x.zip/a.shp"):
            with self.subTest(source=source):
                self.assertTrue(tool.has_network_access({"source": source}))
        for source in ("/data/roads.gpkg|layername=roads", "C:/data/roads.shp", ""):
            with self.subTest(source=source):
                self.assertFalse(tool.has_network_access({"source": source}))


class TableExportTest(unittest.TestCase):
    def test_a_table_without_geometry_is_not_exported_to_a_shapefile(self):
        table = type("Table", (), {"name": lambda self: "stats", "isSpatial": lambda self: False})()
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(export_layer, "_require_vector", lambda name, layer_id="": table),
            self.assertRaisesRegex(ValueError, "has no geometry.*\\.csv or \\.gpkg"),
        ):
            export_layer.ExportLayerTool().prepare({"layer_name": "stats", "path": f"{folder}/stats.shp"})


class BasemapConnectorTest(unittest.TestCase):
    def test_a_connector_switched_off_takes_its_tiles_with_it(self):
        tool = add_basemap.AddBasemapTool()
        with (
            mock.patch.object(add_basemap, "disabled_connectors", lambda: frozenset({"openstreetmap"})),
            mock.patch.object(add_basemap, "layer_names", lambda: []),
        ):
            with self.assertRaisesRegex(ValueError, "OpenStreetMap connector is turned off"):
                tool.prepare({"preset": "osm"})
            with self.assertRaisesRegex(ValueError, "turned off"):
                tool.prepare({"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "name": "mine"})
            self.assertEqual(tool.prepare({"preset": "carto-positron"})["name"], "CARTO Positron")


class NullPropertyTest(unittest.TestCase):
    def test_a_null_value_is_a_key_left_unused(self):
        params = {"properties": {"name": None, "visible": True, "group": None}}
        self.assertEqual(properties_of(params, "layer"), {"visible": True})

    def test_an_empty_layer_name_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            configure_layer._check_name({"name": "  "}, "roads")
        configure_layer._check_name({"visible": True}, "roads")


if __name__ == "__main__":
    unittest.main()
