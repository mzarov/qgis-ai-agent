"""Keys inside layer sources never reach the model, whichever tool or briefing reads the layers."""

import json
import unittest
from unittest import mock
from urllib.parse import quote, unquote

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.core.context import project as context
from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.common.layer_meta import MASKED_VALUE
from ai_agent.qgis_tools.inspect import list_layers as list_layers_module
from ai_agent.qgis_tools.inspect.describe_layer import DescribeLayerTool
from ai_agent.qgis_tools.inspect.list_layers import ListLayersTool
from ai_agent.qgis_tools.processing import list_processing_history as history_module
from ai_agent.qgis_tools.processing.list_processing_history import ListProcessingHistoryTool
from ai_agent.qgis_tools.project.add_basemap import _xyz_source

TILES = "https://tiles.example/{z}/{x}/{y}.png"
PROXIED = "https://proxy.example/tiles?target=" + quote(f"{TILES}?key=FAKE-NESTED-KEY", safe="")


def xyz(url):
    """An XYZ source as QGIS 4.2 keeps it: QgsDataSourceUri.encodedUri() percent-encodes the nested URL whole."""
    return f"type=xyz&url={quote(url, safe='')}"


SOURCES = {
    "reported": (
        "type=xyz&url=https%3A%2F%2Ftiles.example%2F%7Bz%7D%2F%7Bx%7D%2F%7By%7D.png%3Fapi_key%3DSUPERSECRET",
        "raster",
    ),
    "plugin basemap": (_xyz_source(f"{TILES}?api_key=FAKE-PLUGIN-KEY&style=dark"), "raster"),
    "subscription": (xyz(f"{TILES}?subscription-key=FAKE-SUBSCRIPTION-KEY"), "raster"),
    "userinfo": (
        xyz("https://alice:FAKE-USERINFO@tiles.example/{z}/{x}/{y}.png"),  # pragma: allowlist secret
        "raster",
    ),
    "proxied": (xyz(PROXIED) + "&zmax=19", "raster"),
    "header": (xyz(TILES) + "&http-header:x-api-key=FAKE-HEADER-KEY", "raster"),
    "wms": (
        "layers=roads&url=https%3A%2F%2Fwms.example%2Fows%3Ftoken%3DFAKE-WMS-TOKEN"
        "&username=alice&password=FAKE-WMS-PASSWORD",
        "raster",
    ),
    "postgis": (
        "dbname='gis' host=db.example user='gis' password='FAKE-PG-PASSWORD' key='gid' "  # pragma: allowlist secret
        'table="public"."roads" (geom)',
        "vector",
    ),
}
PROVIDERS = {"raster": "wms", "vector": "postgres"}
SECRETS = (
    "SUPERSECRET",
    "FAKE-PLUGIN-KEY",
    "FAKE-SUBSCRIPTION-KEY",
    "FAKE-USERINFO",
    "FAKE-NESTED-KEY",
    "FAKE-HEADER-KEY",
    "FAKE-WMS-TOKEN",
    "FAKE-WMS-PASSWORD",
    "FAKE-PG-PASSWORD",
)


class _Crs:
    def authid(self):
        return "EPSG:3857"

    def isValid(self):
        return True

    def isGeographic(self):
        return False

    def projectionAcronym(self):
        return "merc"


class _SourceLayer:
    """The getters the inspect tools and the briefing read; everything else fails as a broken layer would."""

    def __init__(self, name, source):
        self._name = name
        self._source = source

    def name(self):
        return self._name

    def id(self):
        return f"{self._name}_id"

    def source(self):
        return self._source

    def providerType(self):
        return "wms"

    def isValid(self):
        return True

    def crs(self):
        return _Crs()

    def opacity(self):
        return 1.0

    def extent(self):
        raise RuntimeError("no extent offline")

    def renderer(self):
        return None


class _Raster(_SourceLayer, QgsRasterLayer):
    def width(self):
        return 256

    def height(self):
        return 256

    def bandCount(self):
        return 3


class _Vector(_SourceLayer, QgsVectorLayer):
    def providerType(self):
        return "postgres"

    def geometryType(self):
        raise RuntimeError("geometry is not read here")

    def fields(self):
        return []

    def subsetString(self):
        return ""

    def selectedFeatureCount(self):
        return 0


class _Project:
    def __init__(self, layers):
        self._layers = {layer.id(): layer for layer in layers}

    def mapLayers(self):
        return dict(self._layers)

    def mapLayersByName(self, name):
        return [layer for layer in self._layers.values() if layer.name() == name]

    def crs(self):
        return _Crs()

    def ellipsoid(self):
        return "NONE"


class _Entry:
    def __init__(self, identifier, entry):
        self.id = identifier
        self.entry = entry
        self.timestamp = "2026-10-17T10:00:00"


class _History:
    def __init__(self, entries):
        self.entries = entries

    def queryEntries(self, start, end, provider):
        return list(self.entries)


def _run(source, kind):
    """A Processing run as QGIS records it (`asMap`): the layer is its whole source, its provider in front."""
    layer = f"{PROVIDERS[kind]}://{source}"
    return {
        "algorithm_id": "native:buffer",
        "parameters": {"inputs": {"INPUT": layer, "DISTANCE": 10}},
        "results": {"OUTPUT": layer},
    }


class SourceSecretsTest(unittest.TestCase):
    def setUp(self):
        made = {"raster": _Raster, "vector": _Vector}
        self.layers = [made[kind](name, source) for name, (source, kind) in SOURCES.items()]
        holder = type("ProjectHolder", (), {"instance": staticmethod(lambda: _Project(self.layers))})
        for module in (layers_module, list_layers_module, context, history_module):
            patcher = mock.patch.object(module, "QgsProject", holder)
            patcher.start()
            self.addCleanup(patcher.stop)
        entries = [_Entry(index, _run(source, kind)) for index, (source, kind) in enumerate(SOURCES.values())]
        gui = type("Gui", (), {"historyProviderRegistry": staticmethod(lambda: _History(entries))})
        patcher = mock.patch.object(history_module, "QgsGui", gui)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_no_secret(self, payload, label):
        text = json.dumps(payload, ensure_ascii=False)
        for secret in SECRETS:
            self.assertNotIn(secret, text, f"{label} leaks {secret}")
            self.assertNotIn(secret, unquote(unquote(text)), f"{label} leaks {secret} once decoded")

    def test_describe_layer_hides_every_key_and_still_names_the_source(self):
        for name in SOURCES:
            with self.subTest(layer=name):
                payload = DescribeLayerTool().execute({"layer_name": name})
                self.assert_no_secret(payload, f"describe_layer({name})")
                self.assertIn(".example", unquote(payload["source"]))
                self.assertIn(MASKED_VALUE, unquote(unquote(payload["source"])))

    def test_layer_lists_and_the_briefing_carry_no_key(self):
        self.assert_no_secret(ListLayersTool().execute({}), "list_layers")
        self.assert_no_secret(context.get_project_context(), "project context")
        self.assert_no_secret(context.layer_choices(), "composer layer list")

    def test_processing_history_hides_the_keys_in_recorded_layer_sources(self):
        payload = ListProcessingHistoryTool().execute({"limit": len(SOURCES)})
        self.assertEqual(len(payload["entries"]), len(SOURCES))
        self.assert_no_secret(payload, "list_processing_history")


if __name__ == "__main__":
    unittest.main()
