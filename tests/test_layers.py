import unittest

from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.common.layer_meta import sanitize_source
from ai_agent.qgis_tools.common.layers import (
    LAYER_PINS_KEY,
    bind_layer_reference,
    find_layer_by_id,
    find_layer_by_name,
    layer_pin_error,
    pin_layer_references,
    utm_authid,
)


class Extent:
    def __init__(self, x1, y1, x2, y2):
        self._box = (x1, y1, x2, y2)

    def xMinimum(self):
        return self._box[0]

    def yMinimum(self):
        return self._box[1]

    def xMaximum(self):
        return self._box[2]

    def yMaximum(self):
        return self._box[3]


class Layer:
    def __init__(self, *box):
        self._extent = Extent(*box) if box else None

    def extent(self):
        if self._extent is None:
            raise RuntimeError("нет охвата")
        return self._extent


class UtmZoneTest(unittest.TestCase):
    def test_sverdlovsk_region(self):
        self.assertEqual(utm_authid(Layer(57, 56, 64, 62)), "EPSG:32641")

    def test_moscow(self):
        self.assertEqual(utm_authid(Layer(36, 55, 38, 56)), "EPSG:32637")

    def test_southern_hemisphere(self):
        self.assertEqual(utm_authid(Layer(150, -34, 152, -33)), "EPSG:32756")

    def test_projected_coordinates_fall_back(self):
        self.assertEqual(utm_authid(Layer(-755412, 6195260, 1594380, 6898448)), "EPSG:3857")

    def test_broken_layer_falls_back(self):
        self.assertEqual(utm_authid(Layer()), "EPSG:3857")


class SanitizeSourceTest(unittest.TestCase):
    def test_postgis_password_is_hidden(self):
        source = "dbname='gis' host=db user='mzarov' password='S3cr3t!' table=roads"
        cleaned = sanitize_source(source)
        self.assertNotIn("S3cr3t", cleaned)
        self.assertIn("<hidden>", cleaned)

    def test_uppercase_key_is_hidden(self):
        self.assertNotIn("Qwerty", sanitize_source("user=admin PASSWORD=Qwerty123"))

    def test_token_in_url_is_hidden(self):
        self.assertNotIn("abc123", sanitize_source('url=https://x/wms?token="abc123"'))

    def test_apikey_is_hidden(self):
        self.assertNotIn("DEADBEEF", sanitize_source("url=https://x&apikey=DEADBEEF"))

    def test_url_userinfo_is_hidden(self):
        cleaned = sanitize_source("https://alice:secret@db.example/data")
        self.assertNotIn("alice", cleaned)
        self.assertNotIn("secret", cleaned)
        self.assertIn("db.example", cleaned)

    def test_s3_and_azure_signed_url_credentials_are_hidden(self):
        source = "https://bucket.s3/x?X-Amz-Credential=AKIA_TEST&X-Amz-Signature=deadbeef&sig=azure-supersecret"
        cleaned = sanitize_source(source)
        for secret in ("AKIA_TEST", "deadbeef", "azure-supersecret"):
            self.assertNotIn(secret, cleaned)
        self.assertIn("<hidden>", cleaned)

    def test_primary_key_column_is_kept(self):
        self.assertIn("key='gid'", sanitize_source("dbname='g' key='gid' password='x'"))

    def test_url_key_query_value_is_redacted(self):
        cleaned = sanitize_source("https://tiles.example/data?key=DEADBEEF&layer=roads")
        self.assertNotIn("DEADBEEF", cleaned)
        self.assertIn("layer=roads", cleaned)

    def test_file_path_untouched(self):
        path = "/Users/mzarov/data/Города.shp|layerid=0"
        self.assertEqual(sanitize_source(path), path)

    def test_long_source_is_truncated(self):
        self.assertLessEqual(len(sanitize_source("x" * 900)), 320)


class NamedLayer:
    def __init__(self, identifier, name):
        self._identifier = identifier
        self._name = name

    def id(self):
        return self._identifier

    def name(self):
        return self._name


class LayerProject:
    def __init__(self, layers):
        self.layers = {layer.id(): layer for layer in layers}

    def mapLayers(self):
        return dict(self.layers)

    def mapLayersByName(self, name):
        return [layer for layer in self.layers.values() if layer.name() == name]


class LayerIdentityTest(unittest.TestCase):
    def setUp(self):
        self.first = NamedLayer("roads_a", "roads")
        self.second = NamedLayer("roads_b", "roads")
        project = LayerProject([self.first, self.second])
        self.saved = layers_module.QgsProject
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})

    def tearDown(self):
        layers_module.QgsProject = self.saved

    def test_duplicate_exact_names_are_never_resolved_by_order(self):
        with self.assertRaises(ValueError) as caught:
            find_layer_by_name("roads")
        message = str(caught.exception)
        self.assertIn("ambiguous", message)
        self.assertIn("roads_a", message)
        self.assertIn("roads_b", message)

    def test_case_insensitive_fallback_is_also_ambiguity_safe(self):
        project = LayerProject([NamedLayer("upper", "Roads"), NamedLayer("caps", "ROADS")])
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        with self.assertRaises(ValueError) as caught:
            find_layer_by_name("roads")
        self.assertIn("ambiguous", str(caught.exception))

    def test_layer_id_selects_one_stable_target(self):
        self.assertIs(find_layer_by_id("roads_b"), self.second)

    def test_duplicate_names_accept_a_matching_explicit_id(self):
        prepared = pin_layer_references({"layer_name": "roads", "layer_id": "roads_b"})
        self.assertEqual(prepared[LAYER_PINS_KEY], [{"name": "roads", "id": "roads_b"}])

    def test_id_and_case_insensitive_name_accept_the_same_layer(self):
        prepared = pin_layer_references({"layer_name": "ROADS", "layer_id": "roads_b"})
        self.assertEqual(prepared[LAYER_PINS_KEY], [{"name": "roads", "id": "roads_b"}])

    def test_prepared_reference_keeps_both_human_name_and_stable_id(self):
        prepared = bind_layer_reference({"layer_name": "roads"}, self.second)
        self.assertEqual(prepared["layer_name"], "roads")
        self.assertEqual(prepared["layer_id"], "roads_b")

    def test_hidden_pin_detects_a_same_name_replacement(self):
        project = LayerProject([NamedLayer("old", "roads")])
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        prepared = pin_layer_references({"layer_name": "roads"})
        self.assertEqual(layer_pin_error(prepared), "")

        project.layers = {"new": NamedLayer("new", "roads")}

        self.assertIn("changed or disappeared", layer_pin_error(prepared))

    def test_name_and_id_must_identify_the_same_layer(self):
        project = LayerProject([NamedLayer("roads", "roads"), NamedLayer("rivers", "rivers")])
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})

        with self.assertRaisesRegex(ValueError, "identify different layers"):
            pin_layer_references({"layer_name": "roads", "layer_id": "rivers"})

        prepared = pin_layer_references({"layer_name": "roads", "layer_id": "roads"})
        self.assertEqual(prepared[LAYER_PINS_KEY], [{"name": "roads", "id": "roads"}])

    def test_caller_cannot_forge_hidden_layer_pins(self):
        project = LayerProject([NamedLayer("roads", "roads"), NamedLayer("rivers", "rivers")])
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        prepared = pin_layer_references(
            {
                "layer_id": "roads",
                LAYER_PINS_KEY: [{"name": "rivers", "id": "rivers"}],
            }
        )

        self.assertEqual(prepared[LAYER_PINS_KEY], [{"name": "roads", "id": "roads"}])

    def test_forged_hidden_pin_without_a_public_reference_is_removed(self):
        prepared = pin_layer_references({LAYER_PINS_KEY: [{"name": "roads", "id": "roads"}]})

        self.assertNotIn(LAYER_PINS_KEY, prepared)

    def test_layer_name_lists_are_pinned_as_a_set_of_exact_targets(self):
        project = LayerProject([NamedLayer("roads", "roads"), NamedLayer("rivers", "rivers")])
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        prepared = pin_layer_references({"layer_names": ["roads", "rivers"]})

        project.layers.pop("rivers")

        self.assertIn("rivers", layer_pin_error(prepared))


if __name__ == "__main__":
    unittest.main()
