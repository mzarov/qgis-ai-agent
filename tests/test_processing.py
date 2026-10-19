import unittest
from unittest import mock

from ai_agent.qgis_tools.processing import utils
from ai_agent.qgis_tools.processing.utils import (
    _coerce_enum_value,
    coerce_parameters,
    destination_parameter_names,
)


class CoerceEnumTest(unittest.TestCase):
    OPTIONS = ["Round", "Flat", "Square"]

    def test_label_becomes_index(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "Round"), 0)

    def test_label_is_case_insensitive(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "flat"), 1)
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "SQUARE"), 2)

    def test_index_is_kept(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, 2), 2)

    def test_numeric_string_becomes_index(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "1"), 1)

    def test_unknown_label_passes_through(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "Нет такого"), "Нет такого")

    def test_bool_is_not_treated_as_index(self):
        self.assertIs(_coerce_enum_value(self.OPTIONS, True), True)


class _Parameter:
    def __init__(self, name, kind, destination=False):
        self._name = name
        self._kind = kind
        self._destination = destination

    def name(self):
        return self._name

    def type(self):
        return self._kind

    def isDestination(self):
        return self._destination


class _Algorithm:
    def __init__(self, *parameters):
        self._parameters = parameters

    def parameterDefinitions(self):
        return self._parameters


class _Layer:
    @staticmethod
    def id():
        return "roads-id"


class _Project:
    @staticmethod
    def mapLayer(identifier):
        return _Layer() if identifier == "roads-id" else None


class ProcessingParameterIdentityTest(unittest.TestCase):
    def setUp(self):
        self.saved_project = utils.QgsProject
        self.saved_find = utils.find_layer_by_name
        utils.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: _Project())})
        utils.find_layer_by_name = lambda name: _Layer()

    def tearDown(self):
        utils.QgsProject = self.saved_project
        utils.find_layer_by_name = self.saved_find

    def test_generic_and_multilayer_inputs_are_pinned_to_layer_ids(self):
        algorithm = _Algorithm(_Parameter("INPUT", "layer"), _Parameter("LAYERS", "multilayer"))
        prepared = coerce_parameters(
            algorithm,
            {"INPUT": "roads", "LAYERS": ["roads"]},
        )
        self.assertEqual(prepared, {"INPUT": "roads-id", "LAYERS": ["roads-id"]})

    def test_destination_detection_uses_qgis_destination_contract(self):
        algorithm = _Algorithm(_Parameter("VECTOR", "vectorTileDestination", destination=True))
        self.assertEqual(destination_parameter_names(algorithm), ["VECTOR"])


class _Loaded:
    def __init__(self, layer_id, source, name):
        self._id, self._source, self._name = layer_id, source, name

    def id(self):
        return self._id

    def source(self):
        return self._source

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name


class _LoadedProject:
    def __init__(self, *layers):
        self._layers = {layer.id(): layer for layer in layers}

    def mapLayers(self):
        return dict(self._layers)

    def mapLayer(self, identifier):
        return self._layers.get(identifier)


class OutputNameTest(unittest.TestCase):
    PATH = "/data/centres.gpkg"

    def setUp(self):
        self.earlier = _Loaded("earlier-id", self.PATH, "old centres")
        self.loaded = _Loaded("centres-id", self.PATH, "Centroids")
        self.memory = _Loaded("buffered-id", "Polygon?crs=EPSG:3857&uid={1}", "Buffered")
        project = _LoadedProject(self.earlier, self.loaded, self.memory)
        self.saved = (utils.QgsProject, utils.find_layer_by_name)
        utils.QgsProject = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        utils.find_layer_by_name = _not_found

    def tearDown(self):
        utils.QgsProject, utils.find_layer_by_name = self.saved

    def test_a_file_output_names_the_layer_loaded_from_it_not_an_earlier_one(self):
        self.assertEqual(utils.apply_output_name({"OUTPUT": self.PATH}, "Desired", {"earlier-id"}), "Desired")
        self.assertEqual((self.loaded.name(), self.earlier.name()), ("Desired", "old centres"))

    def test_a_geopackage_layer_suffix_still_reads_as_the_file(self):
        self.loaded._source = f"{self.PATH}|layername=centres"
        self.assertIs(utils.output_layer(self.PATH, {"earlier-id"}), self.loaded)

    def test_a_temporary_output_is_still_found_by_its_id(self):
        self.assertEqual(utils.apply_output_name({"OUTPUT": "buffered-id"}, "Desired", {"earlier-id"}), "Desired")
        self.assertEqual(self.memory.name(), "Desired")

    def test_an_empty_file_output_is_warned_about_too(self):
        with mock.patch.object(utils, "feature_count_if_cheap", return_value=0):
            warnings = utils.empty_output_warnings({"OUTPUT": self.PATH}, {"earlier-id"})
        self.assertEqual(len(warnings), 1)
        self.assertIn("'Centroids' has no features", warnings[0])

    def test_a_file_no_layer_of_the_run_reads_is_not_named(self):
        everything = {"earlier-id", "centres-id", "buffered-id"}
        self.assertEqual(utils.apply_output_name({"OUTPUT": self.PATH}, "Desired", everything), "")
        self.assertEqual(utils.output_layer("/data/elsewhere.gpkg"), None)


def _not_found(name):
    raise ValueError(f"Layer not found: '{name}'.")


if __name__ == "__main__":
    unittest.main()
