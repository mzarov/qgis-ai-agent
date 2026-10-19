import unittest

from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.common.layer_meta import sanitize_source
from ai_agent.qgis_tools.common.layers import (
    LAYER_PINS_KEY,
    bind_layer_reference,
    find_layer_by_id,
    find_layer_by_name,
    layer_pin_error,
    local_project_crs,
    pin_layer_references,
    utm_at,
    utm_authid,
    with_layer_names,
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

    def test_a_point_outside_degrees_has_no_zone(self):
        self.assertEqual(utm_at(37.6, 55.7), "EPSG:32637")
        self.assertEqual(utm_at(4_190_000.0, 7_500_000.0), "")


class Crs:
    def __init__(self, authid, acronym, geographic=False, valid=True):
        self._authid, self._acronym, self._geographic, self._valid = authid, acronym, geographic, valid

    def isValid(self):
        return self._valid

    def isGeographic(self):
        return self._geographic

    def projectionAcronym(self):
        return self._acronym

    def authid(self):
        return self._authid


class Project:
    def __init__(self, crs):
        self._crs = crs

    def crs(self):
        return self._crs


class LocalProjectCrsTest(unittest.TestCase):
    def test_a_national_grid_is_kept(self):
        self.assertEqual(local_project_crs(Project(Crs("EPSG:27700", "tmerc"))), "EPSG:27700")

    def test_web_mercator_and_world_maps_are_not(self):
        for authid, acronym in (("EPSG:3857", "merc"), ("EPSG:4087", "eqc"), ("ESRI:54030", "robin")):
            with self.subTest(authid):
                self.assertEqual(local_project_crs(Project(Crs(authid, acronym))), "")

    def test_degrees_and_a_broken_crs_are_not(self):
        self.assertEqual(local_project_crs(Project(Crs("EPSG:4326", "longlat", geographic=True))), "")
        self.assertEqual(local_project_crs(Project(Crs("", "", valid=False))), "")
        self.assertEqual(local_project_crs(object()), "")


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

    def test_a_key_in_an_encoded_tile_url_is_hidden_and_the_url_encoded_again(self):
        source = (
            "type=xyz&url=https%3A%2F%2Ftiles.example%2F%7Bz%7D%2F%7Bx%7D%2F%7By%7D.png"
            "%3Fapi_key%3DSUPERSECRET%26style%3Ddark&zmax=19"
        )
        self.assertEqual(
            sanitize_source(source),
            "type=xyz&url=https%3A%2F%2Ftiles.example%2F%7Bz%7D%2F%7Bx%7D%2F%7By%7D.png"
            "%3Fapi_key%3D<hidden>%26style%3Ddark&zmax=19",
        )

    def test_a_clean_provider_uri_is_left_exactly_as_it_is(self):
        source = "type=xyz&url=https%3A%2F%2Ftile.openstreetmap.org%2F%7Bz%7D%2F%7Bx%7D%2F%7By%7D.png&zmax=19&zmin=0"
        self.assertEqual(sanitize_source(source), source)
        delimited = "file:///Users/mzarov/data/points.csv?type=csv&delimiter=%3B&xField=lon&yField=lat&crs=EPSG:4326"
        self.assertEqual(sanitize_source(delimited), delimited)

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


class LayerNamesShownTest(unittest.TestCase):
    def setUp(self):
        self.project = LayerProject(
            [NamedLayer("stations_98c97027", "stations"), NamedLayer("roads_1", "roads"), NamedLayer("blank_1", " ")]
        )
        self.saved = layers_module.QgsProject
        layers_module.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: self.project)})

    def tearDown(self):
        layers_module.QgsProject = self.saved

    def test_pinned_ids_read_as_current_names_at_any_depth(self):
        params = {
            "algorithm_id": "native:buffer",
            "parameters": {"INPUT": "stations_98c97027", "LAYERS": ["roads_1", "stations_98c97027"], "DISTANCE": 5},
            "layer_id": "roads_1",
        }
        shown = with_layer_names(params)
        self.assertEqual(shown["parameters"], {"INPUT": "stations", "LAYERS": ["roads", "stations"], "DISTANCE": 5})
        self.assertEqual(shown["layer_id"], "roads")
        self.assertEqual(shown["algorithm_id"], "native:buffer")
        self.assertEqual(params["parameters"]["INPUT"], "stations_98c97027", "the queued call must keep its ids")

    def test_a_rename_shows_the_new_name(self):
        self.project.layers["stations_98c97027"] = NamedLayer("stations_98c97027", "metro stations")
        self.assertEqual(
            with_layer_names({"parameters": {"INPUT": "stations_98c97027"}})["parameters"]["INPUT"], "metro stations"
        )

    def test_ids_stay_where_a_name_would_not_identify_the_layer(self):
        self.project.layers["roads_2"] = NamedLayer("roads_2", "roads")
        shown = with_layer_names(
            {"a": "roads_1", "b": "gone_7", "c": "blank_1", "d": "TEMPORARY_OUTPUT", "e": "x roads_1"}
        )
        self.assertEqual(
            shown, {"a": "roads_1", "b": "gone_7", "c": "blank_1", "d": "TEMPORARY_OUTPUT", "e": "x roads_1"}
        )

    def test_private_keys_keep_their_ids(self):
        params = pin_layer_references({"layer_name": "stations"})
        self.assertEqual(with_layer_names(params)[LAYER_PINS_KEY], [{"name": "stations", "id": "stations_98c97027"}])

    def test_a_failing_project_leaves_the_arguments_as_they_are(self):
        class Broken:
            def name(self):
                raise RuntimeError("wrapped C++ object has been deleted")

        self.project.layers["broken"] = Broken()
        params = {"INPUT": "stations_98c97027"}
        self.assertIs(with_layer_names(params), params)
        self.assertEqual(with_layer_names("not a dict"), "not a dict")


class GeometryNameTest(unittest.TestCase):
    def test_qt6_int_enum_members_are_named_by_their_name(self):
        import enum

        from qgis.core import QgsVectorLayer

        from ai_agent.qgis_tools.common.layers import geometry_type_name

        class GeometryType(enum.IntEnum):
            Point = 0
            Line = 1
            Polygon = 2

        for member, expected in (
            (GeometryType.Point, "point"),
            (GeometryType.Line, "line"),
            (GeometryType.Polygon, "polygon"),
        ):
            layer = QgsVectorLayer()
            layer.geometryType = lambda member=member: member
            self.assertEqual(str(member), str(int(member)))
            self.assertEqual(geometry_type_name(layer), expected)


class EnumNameTest(unittest.TestCase):
    def test_int_enum_members_give_their_names(self):
        import enum

        from ai_agent.qgis_tools.common.layers import enum_name, field_type_name

        class Type(enum.IntEnum):
            Double = 6
            QString = 10

        self.assertEqual(enum_name(Type.Double), "Double")
        self.assertEqual(enum_name("Qgis.GeometryType.Polygon"), "Polygon")

        class Field:
            def __init__(self, provider_name, kind):
                self.provider_name, self.kind = provider_name, kind

            def typeName(self):
                return self.provider_name

            def type(self):
                return self.kind

        self.assertEqual(field_type_name(Field("", Type.Double)), "double")
        self.assertEqual(field_type_name(Field("", Type.QString)), "string")
        self.assertEqual(field_type_name(Field("Integer64", Type.Double)), "Integer64")


if __name__ == "__main__":
    unittest.main()
