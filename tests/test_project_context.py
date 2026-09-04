import unittest

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

    def test_an_empty_project_is_one_line(self):
        self.use(Project([], crs=""))
        self.assertEqual(context.get_project_context(), context.NO_LAYERS)

    def test_the_list_is_capped_with_a_remainder(self):
        self.use(Project([Layer(f"l{index}") for index in range(15)], crs=""))
        self.assertTrue(context.get_project_context().endswith("and 3 more."))


if __name__ == "__main__":
    unittest.main()
