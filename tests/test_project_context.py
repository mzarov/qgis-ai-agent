import json
import unittest
from pathlib import Path
from unittest import mock

from ai_agent.core.context import project as context


class Layer:
    def __init__(self, name, provider="ogr", count=17, selected=0, fail_count=False):
        self._name = name
        self._provider = provider
        self._count = count
        self._selected = selected
        self._fail = fail_count

    def name(self):
        return self._name

    def providerType(self):
        return self._provider

    def featureCount(self):
        if self._fail:
            raise RuntimeError("must not be asked")
        return self._count

    def selectedFeatureCount(self):
        return self._selected


class Project:
    def __init__(self, layers, crs="EPSG:3857"):
        self._layers = layers
        self._crs = crs

    def crs(self):
        return self

    def authid(self):
        return self._crs

    def mapLayers(self):
        return {str(index): layer for index, layer in enumerate(self._layers)}


class ProjectContextTest(unittest.TestCase):
    def setUp(self):
        self.saved = (
            context.QgsProject,
            context.layer_kind,
            context.geometry_type_name,
            context.crs_authid,
            context.active_layer_name,
        )
        context.layer_kind = lambda layer: "raster" if layer.name().startswith("dem") else "vector"
        context.geometry_type_name = lambda layer: "point"
        context.crs_authid = lambda layer: "EPSG:4326"
        context.active_layer_name = lambda: ""

    def tearDown(self):
        (
            context.QgsProject,
            context.layer_kind,
            context.geometry_type_name,
            context.crs_authid,
            context.active_layer_name,
        ) = self.saved

    def use(self, project):
        class Holder:
            @staticmethod
            def instance():
                return project

        context.QgsProject = Holder

    def test_a_local_layer_reports_count_and_selection(self):
        line = context.describe_layer_line(Layer("cafes", selected=3))
        self.assertEqual(line, "cafes (point, EPSG:4326, 17 features, 3 selected)")

    def test_a_remote_layer_is_not_counted_and_not_even_asked(self):
        line = context.describe_layer_line(Layer("roads", provider="postgres", fail_count=True))
        self.assertEqual(line, "roads (point, EPSG:4326)")

    def test_a_raster_has_no_feature_facts(self):
        line = context.describe_layer_line(Layer("dem", provider="gdal", fail_count=True))
        self.assertEqual(line, "dem (raster, EPSG:4326)")

    def test_unknown_counts_are_left_out(self):
        self.assertEqual(context.describe_layer_line(Layer("odd", count=-1)), "odd (point, EPSG:4326)")

    def test_context_names_project_crs_active_layer_and_layers(self):
        self.use(Project([Layer("cafes")]))
        context.active_layer_name = lambda: "cafes"
        self.assertEqual(
            context.get_project_context(),
            "Project CRS: EPSG:3857.\nActive layer: cafes.\nLayers: cafes (point, EPSG:4326, 17 features).",
        )

    def test_measurements_name_the_ellipsoid_and_unit_codes(self):
        class Measured:
            def __init__(self, ellipsoid):
                self._ellipsoid = ellipsoid

            def ellipsoid(self):
                return self._ellipsoid

            def distanceUnits(self):
                return "distance"

            def areaUnits(self):
                return "area"

        class Units:
            @staticmethod
            def encodeUnit(unit):
                return {"distance": "meters", "area": "m2"}[unit]

        with mock.patch.object(context, "QgsUnitTypes", Units):
            self.assertEqual(
                context.measurement_line(Measured("EPSG:7030")),
                "Measurements: ellipsoid EPSG:7030; $length in meters, $area in m2, even on layers in degrees.",
            )
            self.assertEqual(context.measurement_line(Measured("NONE")), context.UNMEASURED)
        self.assertEqual(context.measurement_line(object()), "", "a project that cannot say adds no line")

    def test_without_an_ellipsoid_the_line_names_where_to_measure_in_metres(self):
        class Unmeasured:
            def ellipsoid(self):
                return "NONE"

        with mock.patch.object(context, "project_metric_crs", lambda project: "EPSG:32637"):
            line = context.measurement_line(Unmeasured())
        self.assertTrue(line.startswith(context.UNMEASURED), line)
        self.assertIn("transform the geometry to EPSG:32637 first", line)
        self.assertIn("EPSG:3857 inflates", line)

    def test_the_eval_fixture_describes_measurements_like_the_plugin(self):
        fixture = json.loads((Path(__file__).resolve().parent.parent / "evals" / "fixture.json").read_text())
        line = next(item for item in fixture["project_context"].splitlines() if item.startswith("Measurements:"))
        self.assertEqual(line, context.MEASURED.format("EPSG:7030", "meters", "m2"))

    def test_the_model_reads_each_layers_fields_with_their_types(self):
        class Field:
            def __init__(self, name, kind):
                self._name, self._kind = name, kind

            def name(self):
                return self._name

            def typeName(self):
                return self._kind

        class Fielded(Layer):
            def __init__(self, name, fields):
                super().__init__(name)
                self._fields = fields

            def fields(self):
                return self._fields

        cafes = Fielded("cafes", [Field("name", "String"), Field("seats", "Integer")])
        self.assertEqual(
            context.context_line(cafes), "cafes (point, EPSG:4326, 17 features; fields: name:String, seats:Integer)"
        )
        wide = Fielded("census", [Field(f"c{index}", "Real") for index in range(context.MAX_CONTEXT_FIELDS + 4)])
        self.assertTrue(context.context_line(wide).endswith("c14:Real and 4 more)"))
        self.assertEqual(context.context_line(Layer("bare")), "bare (point, EPSG:4326, 17 features)")
        self.use(Project([cafes]))
        context.active_layer_name = lambda: ""
        self.assertIn("fields: name:String", context.get_project_context())

    def test_an_empty_project_is_one_line(self):
        self.use(Project([], crs=""))
        self.assertEqual(context.get_project_context(), context.NO_LAYERS)

    def test_layer_choices_feed_the_mention_list(self):
        self.use(Project([Layer("rivers"), Layer("Cafes", selected=2)]))
        choices = context.layer_choices()
        self.assertEqual([name for name, _, _ in choices], ["Cafes", "rivers"])
        self.assertEqual(choices[0][1], "point, EPSG:4326, 17 features, 2 selected")
        self.assertEqual(choices[0][2], context.LAYER_ORIGIN)

    def test_the_list_is_capped_with_a_remainder(self):
        self.use(Project([Layer(f"l{index}") for index in range(15)], crs=""))
        self.assertTrue(context.get_project_context().endswith("and 3 more."))


if __name__ == "__main__":
    unittest.main()
