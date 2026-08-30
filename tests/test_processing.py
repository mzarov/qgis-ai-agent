import unittest

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

    @staticmethod
    def flags():
        return 0


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


if __name__ == "__main__":
    unittest.main()
