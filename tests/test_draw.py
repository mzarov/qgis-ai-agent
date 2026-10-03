import types
import unittest
from unittest.mock import patch

from qgis.core import QgsVectorLayer

from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE
from ai_agent.qgis_tools.draw import attributes as attributes_module
from ai_agent.qgis_tools.draw import coordinates as coordinates_module
from ai_agent.qgis_tools.draw import targets as targets_module
from ai_agent.qgis_tools.draw.draw_features import DrawFeaturesTool
from ai_agent.qgis_tools.registry import summarize_tool_call

KNOWN_CRS = {"EPSG:4326": True, "EPSG:3857": False, "EPSG:32637": False, "EPSG:32737": False}
MOSCOW = [37.62, 55.75]
KAZAN = [49.11, 55.79]


class FakeCrs:
    def __init__(self, text=""):
        self._text = str(text)

    def isValid(self):
        return self._text in KNOWN_CRS

    def isGeographic(self):
        return KNOWN_CRS.get(self._text, False)

    def authid(self):
        return self._text if self.isValid() else ""

    def toWkt(self):
        return f"WKT[{self._text}]"


class FakePoint:
    def __init__(self, x, y):
        self._x, self._y = float(x), float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class FakeTransform:
    """Moves a point by +1000/+2000, enough to prove the transform ran."""

    def __init__(self, source, target, context=None):
        self.target = target

    def transform(self, point):
        return FakePoint(point.x() + 1000, point.y() + 2000)


class FakeGeometry:
    def __init__(self, kind, points):
        self.kind = kind
        self.points = [(point.x(), point.y()) for point in points]

    @classmethod
    def fromPointXY(cls, point):
        return cls("point", [point])

    @classmethod
    def fromPolylineXY(cls, points):
        return cls("line", points)

    @classmethod
    def fromPolygonXY(cls, rings):
        return cls("polygon", rings[0])

    def isGeosValid(self):
        # A "bow tie" — the second and fourth vertices swapped — crosses itself.
        return self.points != [(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)]


class FakeFields:
    def __init__(self, names, types=None):
        self._names = list(names)
        self._types = dict(types or {})

    def names(self):
        return list(self._names)

    def indexFromName(self, name):
        return self._names.index(name) if name in self._names else -1

    def field(self, name):
        return FakeField(self._types.get(name, "string"))


class FakeField:
    def __init__(self, kind):
        self._kind = kind

    def typeName(self):
        return self._kind

    def convertCompatible(self, value):
        if self._kind == "integer" and not isinstance(value, int):
            raise ValueError(f'Value "{value}" is not a number')
        return value


class FakeFeature:
    def __init__(self, fields=None):
        self.geometry = None
        self.attributes = {}

    def setGeometry(self, geometry):
        self.geometry = geometry

    def setAttribute(self, name, value):
        self.attributes[name] = value


class FakeProvider:
    accept = True

    def __init__(self):
        self.features = []

    def addFeatures(self, features):
        if self.accept:
            self.features.extend(features)
        return self.accept, features


class FakeMemoryLayer:
    def __init__(self, name, fields, wkb, crs):
        self._name = name
        self.schema = fields
        self.wkb = wkb
        self._crs = crs
        self.provider = FakeProvider()

    def isValid(self):
        return True

    def name(self):
        return self._name

    def id(self):
        return f"{self._name}_id"

    def fields(self):
        return self.schema

    def dataProvider(self):
        return self.provider

    def updateExtents(self):
        return None


class FakeMemoryUtils:
    created = []

    @classmethod
    def createMemoryLayer(cls, name, fields, wkb, crs):
        layer = FakeMemoryLayer(name, fields, wkb, crs)
        cls.created.append(layer)
        return layer


class FakeProject:
    def __init__(self, names=()):
        self.names = set(names)
        self.added = []

    def instance(self):
        return self

    def mapLayersByName(self, name):
        return [name] if name in self.names else []

    def addMapLayer(self, layer):
        self.added.append(layer)
        self.names.add(layer.name())


class ExistingLayer(QgsVectorLayer):
    def __init__(self, geometry="Point", provider="ogr", fields=("name", "height"), types=None, editable=False):
        self._geometry = geometry
        self._provider = provider
        self._fields = FakeFields(fields, types)
        self.editing = editable
        self.added = []
        self.commits = 0

    def name(self):
        return "Sights"

    def id(self):
        return "sights_id"

    def geometryType(self):
        return types.SimpleNamespace(name=self._geometry)

    def providerType(self):
        return self._provider

    def crs(self):
        return FakeCrs("EPSG:3857")

    def extent(self):
        return FakeExtent(-50.0, -50.0, 50.0, 50.0)

    def fields(self):
        return self._fields

    def isEditable(self):
        return self.editing

    def startEditing(self):
        self.editing = True
        return True

    def addFeatures(self, features):
        self.added.extend(features)
        return True

    def commitChanges(self):
        self.commits += 1
        self.editing = False
        return True

    def rollBack(self):
        self.editing = False
        return True

    def triggerRepaint(self):
        return None


class FakeExtent:
    def __init__(self, xmin, ymin, xmax, ymax):
        self.edges = (xmin, ymin, xmax, ymax)

    def isEmpty(self):
        return False

    def xMinimum(self):
        return self.edges[0]

    def yMinimum(self):
        return self.edges[1]

    def xMaximum(self):
        return self.edges[2]

    def yMaximum(self):
        return self.edges[3]


class FakeLayerUtils:
    @staticmethod
    def createFeature(layer, geometry, values):
        return {"geometry": geometry, "values": values}

    @staticmethod
    def makeFeatureCompatible(feature, layer):
        return [feature]


class DrawTestBase(unittest.TestCase):
    def setUp(self):
        self.project = FakeProject(names={"Roads"})
        self.layer = ExistingLayer()
        FakeMemoryUtils.created = []
        replacements = [
            patch.object(coordinates_module, "QgsCoordinateReferenceSystem", FakeCrs),
            patch.object(coordinates_module, "QgsPointXY", FakePoint),
            patch.object(coordinates_module, "QgsCoordinateTransform", FakeTransform),
            patch.object(coordinates_module, "QgsGeometry", FakeGeometry),
            patch.object(coordinates_module, "QgsProject", self.project),
            patch.object(targets_module, "QgsProject", self.project),
            patch.object(targets_module, "QgsMemoryProviderUtils", FakeMemoryUtils),
            patch.object(targets_module, "QgsFeature", FakeFeature),
            patch.object(targets_module, "QgsVectorLayerUtils", FakeLayerUtils),
            patch.object(targets_module, "qgs_fields", lambda schema: dict(schema)),
            patch.object(targets_module, "find_layer_by_name", lambda name: self.layer),
            patch.object(targets_module, "find_layer_by_id", lambda identifier: self.layer),
        ]
        for replacement in replacements:
            replacement.start()
            self.addCleanup(replacement.stop)
        self.tool = DrawFeaturesTool()

    def new_point(self, coordinates=MOSCOW, **extra):
        params = {"new_layer_name": "Pins", "geometry": "point", "features": [{"coordinates": [coordinates]}]}
        params.update(extra)
        return params

    def refused(self, params, *fragments):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare(params)
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))
        return str(caught.exception)


class SchemaTest(unittest.TestCase):
    def test_only_geometry_and_features_are_required(self):
        schema = DrawFeaturesTool().get_openai_schema()["function"]["parameters"]
        self.assertEqual(sorted(schema["required"]), ["features", "geometry"])
        self.assertEqual(schema["properties"]["geometry"]["enum"], ["point", "line", "polygon"])
        pair = schema["properties"]["features"]["items"]["properties"]["coordinates"]["items"]
        self.assertEqual(pair, {"type": "array", "items": {"type": "number"}})

    def test_the_tool_belongs_to_the_draw_skill(self):
        self.assertEqual(DrawFeaturesTool().skill, "draw")


class PrepareNewLayerTest(DrawTestBase):
    def test_a_point_lands_in_a_new_layer_with_inferred_fields(self):
        params = self.new_point(
            features=[{"coordinates": [MOSCOW], "attributes": {"name": "Kremlin", "floors": 3, "open": True}}]
        )
        prepared = self.tool.prepare(params)
        self.assertEqual(prepared["crs"], "EPSG:4326")
        self.assertEqual(prepared["layer_crs"], "EPSG:4326")
        self.assertEqual(prepared["fields"], {"name": "text", "floors": "integer", "open": "boolean"})
        self.assertEqual(prepared["features"][0]["coordinates"], [MOSCOW])
        self.assertNotIn("layer_name", prepared, "a new layer must not be pinned as an existing one")

    def test_a_bare_pair_is_accepted_for_a_point(self):
        prepared = self.tool.prepare(self.new_point(features=[{"coordinates": MOSCOW}]))
        self.assertEqual(prepared["features"][0]["coordinates"], [MOSCOW])

    def test_mixed_numbers_become_double_and_declared_types_win(self):
        params = self.new_point(
            features=[
                {"coordinates": [MOSCOW], "attributes": {"height": 3, "built": "1495-01-01"}},
                {"coordinates": [KAZAN], "attributes": {"height": 2.5}},
            ],
            fields={"built": "date", "note": "text"},
        )
        prepared = self.tool.prepare(params)
        self.assertEqual(prepared["fields"], {"built": "date", "note": "text", "height": "double"})
        self.assertEqual(prepared["features"][0]["attributes"]["height"], 3.0)

    def test_utm_picks_the_zone_from_the_coordinates(self):
        prepared = self.tool.prepare(self.new_point(layer_crs="utm"))
        self.assertEqual(prepared["layer_crs"], "EPSG:32637")

    def test_utm_in_the_southern_hemisphere(self):
        prepared = self.tool.prepare(self.new_point([37.62, -5.0], layer_crs="UTM"))
        self.assertEqual(prepared["layer_crs"], "EPSG:32737")

    def test_utm_refuses_the_poles(self):
        self.refused(self.new_point([10.0, 88.0], layer_crs="utm"), "polar")

    def test_an_empty_new_layer_needs_no_features(self):
        prepared = self.tool.prepare(
            {"new_layer_name": "Survey", "geometry": "point", "features": [], "fields": {"name": "text"}}
        )
        self.assertEqual(prepared["features"], [])
        self.assertEqual(prepared["fields"], {"name": "text"})

    def test_a_taken_name_is_refused(self):
        self.refused(self.new_point(new_layer_name="Roads"), "already in the project", "layer_name")

    def test_a_declared_type_rejects_a_value_that_does_not_fit(self):
        params = self.new_point(
            features=[{"coordinates": [MOSCOW], "attributes": {"floors": "many"}}], fields={"floors": "integer"}
        )
        self.refused(params, "floors", "integer")

    def test_a_bad_date_and_an_unknown_type_are_refused(self):
        self.refused(
            self.new_point(features=[{"coordinates": [MOSCOW], "attributes": {"d": "May 9"}}], fields={"d": "date"}),
            "date",
        )
        self.refused(self.new_point(fields={"d": "timestamp"}), "timestamp", "Available")

    def test_duplicate_field_names_ignore_case(self):
        self.refused(self.new_point(fields={"Name": "text", "name": "text"}), "twice")

    def test_nested_attribute_values_are_refused(self):
        self.refused(self.new_point(features=[{"coordinates": [MOSCOW], "attributes": {"tags": ["a"]}}]), "plain value")


class PrepareCoordinatesTest(DrawTestBase):
    def test_an_unknown_crs_is_refused(self):
        self.refused(self.new_point(crs="EPSG:999999"), "Unknown CRS", "EPSG:999999")
        self.refused(self.new_point(layer_crs="nonsense"), "layer_crs")

    def test_an_unknown_geometry_is_refused(self):
        self.refused(self.new_point(geometry="circle"), "circle", "point, line, polygon")

    def test_swapped_latitude_and_longitude_are_caught(self):
        message = self.refused(self.new_point([55.75, 137.62]), "swapped")
        self.assertIn("[137.62, 55.75]", message)

    def test_out_of_range_degrees_are_refused(self):
        self.refused(self.new_point([250.0, 95.0]), "outside the range")

    def test_degrees_with_a_metric_crs_are_caught(self):
        self.refused(self.new_point(crs="EPSG:3857"), "longitude/latitude", "EPSG:4326")

    def test_small_projected_values_pass_once_confirmed_by_layer_crs(self):
        message = self.refused(self.new_point([12.0, 7.0], crs="EPSG:3857"), "local grid", "layer_crs")
        self.assertIn("EPSG:3857", message)
        prepared = self.tool.prepare(self.new_point([12.0, 7.0], crs="EPSG:3857", layer_crs="EPSG:3857"))
        self.assertEqual(prepared["layer_crs"], "EPSG:3857")

    def test_small_projected_values_inside_an_existing_layer_extent_pass(self):
        params = {
            "layer_name": "Sights",
            "geometry": "point",
            "crs": "EPSG:3857",
            "features": [{"coordinates": [[12.0, 7.0]]}],
        }
        self.assertEqual(self.tool.prepare(params)["layer_id"], "sights_id")
        outside = {**params, "features": [{"coordinates": [[120.0, 70.0]]}]}
        self.refused(outside, "looks like longitude/latitude")

    def test_metres_with_a_metric_crs_pass(self):
        prepared = self.tool.prepare(self.new_point([4187000.0, 7508000.0], crs="EPSG:3857"))
        self.assertEqual(prepared["crs"], "EPSG:3857")

    def test_a_line_needs_two_distinct_vertices(self):
        params = {"new_layer_name": "Route", "geometry": "line", "features": [{"coordinates": [MOSCOW, MOSCOW]}]}
        self.refused(params, "at least 2 distinct")

    def test_a_polygon_needs_three_distinct_vertices(self):
        ring = [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]
        params = {"new_layer_name": "Zone", "geometry": "polygon", "features": [{"coordinates": ring}]}
        self.refused(params, "at least 3 distinct")

    def test_a_self_crossing_ring_is_refused(self):
        ring = [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
        params = {"new_layer_name": "Zone", "geometry": "polygon", "features": [{"coordinates": ring}]}
        self.refused(params, "crosses itself")

    def test_a_point_with_two_pairs_is_refused(self):
        self.refused(self.new_point(features=[{"coordinates": [MOSCOW, KAZAN]}]), "exactly one")

    def test_malformed_pairs_are_refused(self):
        for bad in ([["37.6", 55.7]], [[True, 55.7]], [[37.6]], [[37.6, 55.7, 120.0]], [[float("nan"), 1.0]], "x"):
            with self.subTest(bad=bad):
                self.refused(self.new_point(features=[{"coordinates": bad}]))

    def test_features_must_be_a_non_empty_list_of_objects(self):
        self.refused({"layer_name": "Sights", "geometry": "point", "features": []}, "non-empty")
        self.refused(self.new_point(features=["37.6 55.7"]), "must be an object")

    def test_too_many_features_are_refused(self):
        many = [{"coordinates": [MOSCOW]}] * (coordinates_module.MAX_FEATURES + 1)
        self.refused(self.new_point(features=many), "at most")


class PrepareTargetTest(DrawTestBase):
    def test_a_target_is_required(self):
        self.refused({"geometry": "point", "features": [{"coordinates": [MOSCOW]}]}, "new_layer_name", "layer_name")

    def test_both_targets_are_refused(self):
        self.refused(self.new_point(layer_name="Sights"), "not both")

    def test_new_layer_options_are_refused_for_an_existing_layer(self):
        params = {"layer_name": "Sights", "geometry": "point", "features": [{"coordinates": [MOSCOW]}]}
        self.refused({**params, "layer_crs": "utm"}, "new layer only")
        self.refused({**params, "fields": {"a": "text"}}, "new layer only")

    def test_an_existing_layer_is_bound_by_id(self):
        params = {"layer_name": "Sights", "geometry": "point", "features": [{"coordinates": [MOSCOW]}]}
        prepared = self.tool.prepare(params)
        self.assertEqual(prepared["layer_id"], "sights_id")

    def test_the_geometry_must_match_the_layer(self):
        params = {"layer_name": "Sights", "geometry": "line", "features": [{"coordinates": [MOSCOW, KAZAN]}]}
        self.refused(params, "point geometries", "new_layer_name")

    def test_unknown_fields_are_refused_with_suggestions(self):
        params = {
            "layer_name": "Sights",
            "geometry": "point",
            "features": [{"coordinates": [MOSCOW], "attributes": {"nam": "Kremlin"}}],
        }
        self.refused(params, "nam", "Similar fields: name")

    def test_a_value_the_field_cannot_hold_is_refused(self):
        self.layer = ExistingLayer(types={"height": "integer"})
        params = {
            "layer_name": "Sights",
            "geometry": "point",
            "features": [{"coordinates": [MOSCOW], "attributes": {"height": "tall"}}],
        }
        self.refused(params, "height", "integer")

    def test_a_layer_in_an_edit_session_is_refused(self):
        self.layer = ExistingLayer(editable=True)
        params = {"layer_name": "Sights", "geometry": "point", "features": [{"coordinates": [MOSCOW]}]}
        self.refused(params, "edit session")


class SafetyTest(DrawTestBase):
    def test_a_new_scratch_layer_is_an_ordinary_write(self):
        params = self.new_point()
        self.assertEqual(self.tool.safety_for(params), SAFETY_WRITE)
        self.assertFalse(self.tool.has_external_effect(params))

    def test_appending_to_a_scratch_layer_is_an_ordinary_write(self):
        self.layer = ExistingLayer(provider="memory")
        params = {"layer_name": "Sights", "geometry": "point", "features": []}
        self.assertEqual(self.tool.safety_for(params), SAFETY_WRITE)

    def test_appending_to_a_file_commits_and_asks_twice(self):
        params = {"layer_name": "Sights", "geometry": "point", "features": []}
        self.assertEqual(self.tool.safety_for(params), SAFETY_DESTRUCTIVE)
        self.assertTrue(self.tool.has_external_effect(params))
        self.assertIn("Undo", self.tool.detail_call(params))

    def test_an_unresolvable_target_counts_as_external(self):
        with patch.object(targets_module, "find_layer_by_name", side_effect=ValueError("gone")):
            self.assertTrue(self.tool.has_external_effect({"layer_name": "Gone"}))


class ExecuteTest(DrawTestBase):
    def test_a_new_layer_gets_its_features_before_joining_the_project(self):
        params = self.tool.prepare(
            {
                "new_layer_name": "Route",
                "geometry": "line",
                "features": [{"coordinates": [MOSCOW, KAZAN], "attributes": {"name": "M7"}}],
            }
        )
        result = self.tool.execute(params)
        layer = FakeMemoryUtils.created[0]
        self.assertEqual(self.project.added, [layer])
        self.assertEqual(result["added"], 1)
        self.assertTrue(result["created"])
        self.assertEqual(result["layer_name"], "Route")
        feature = layer.provider.features[0]
        self.assertEqual(feature.geometry.kind, "line")
        self.assertEqual(feature.geometry.points, [tuple(MOSCOW), tuple(KAZAN)])
        self.assertEqual(feature.attributes, {"name": "M7"})
        self.assertEqual(layer.schema, {"name": "text"})

    def test_a_utm_layer_receives_transformed_coordinates(self):
        result = self.tool.execute(self.tool.prepare(self.new_point(layer_crs="utm")))
        self.assertEqual(result["crs"], "EPSG:32637")
        feature = FakeMemoryUtils.created[0].provider.features[0]
        self.assertEqual(feature.geometry.points, [(MOSCOW[0] + 1000, MOSCOW[1] + 2000)])

    def test_a_refused_insert_adds_nothing_to_the_project(self):
        with patch.object(FakeProvider, "accept", False), self.assertRaises(ValueError):
            self.tool.execute(self.tool.prepare(self.new_point()))
        self.assertEqual(self.project.added, [])

    def test_appending_commits_one_edit_session_in_the_layer_crs(self):
        params = self.tool.prepare(
            {
                "layer_name": "Sights",
                "geometry": "point",
                "features": [{"coordinates": [MOSCOW], "attributes": {"name": "Kremlin"}}],
            }
        )
        result = self.tool.execute(params)
        self.assertEqual(self.layer.commits, 1)
        self.assertEqual(result["added"], 1)
        self.assertFalse(result["created"])
        self.assertIn("Undo", result["note"])
        added = self.layer.added[0]
        self.assertEqual(added["values"], {0: "Kremlin"})
        self.assertEqual(added["geometry"].points, [(MOSCOW[0] + 1000, MOSCOW[1] + 2000)])


class SummaryTest(unittest.TestCase):
    def test_summaries_name_the_count_and_the_layer(self):
        tool = DrawFeaturesTool()
        new = tool.summarize_call({"new_layer_name": "Pins", "geometry": "point", "features": [{}, {}]})
        self.assertIn("2", new)
        self.assertIn("Pins", new)
        appended = tool.summarize_call({"layer_name": "Sights", "geometry": "polygon", "features": [{}]})
        self.assertIn("Sights", appended)
        by_id = tool.summarize_call({"layer_id": "sights_id", "geometry": "point", "features": [{}]})
        self.assertIn("sights_id", by_id)

    def test_malformed_arguments_never_crash_the_summary(self):
        tool = DrawFeaturesTool()
        for params in ({}, {"features": "x"}, {"geometry": 5, "new_layer_name": 3}, {"layer_name": None}):
            with self.subTest(params=params):
                self.assertTrue(tool.summarize_call(params).strip())
                self.assertTrue(tool.detail_call(params).strip())
        self.assertTrue(summarize_tool_call("draw_features", {"features": None}).strip())


class AttributeHelpersTest(unittest.TestCase):
    def test_booleans_accept_words(self):
        rows = attributes_module.coerced_rows({"open": "boolean"}, [{"open": "yes"}, {"open": "0"}, {"open": None}])
        self.assertEqual([row["open"] for row in rows], [True, False, None])

    def test_integers_refuse_fractions_and_booleans(self):
        for value in (2.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                attributes_module.coerced_rows({"n": "integer"}, [{"n": value}])
