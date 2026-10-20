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


class _Searchable:
    def __init__(self, identifier, name):
        self._identifier, self._name, self.deleted = identifier, name, False

    def _alive(self):
        if self.deleted:
            raise RuntimeError("wrapped C/C++ object of type QgsProcessingModelAlgorithm has been deleted")

    def id(self):
        self._alive()
        return self._identifier

    def displayName(self):
        self._alive()
        return self._name

    def tags(self):
        self._alive()
        return []

    def group(self):
        self._alive()
        return "Models"

    def shortDescription(self):
        self._alive()
        return ""


class _Registry:
    def __init__(self, algorithms):
        self.current = list(algorithms)

    def algorithms(self):
        return list(self.current)


class SearchIndexTest(unittest.TestCase):
    def test_a_refreshed_provider_never_leaves_deleted_algorithms_in_the_results(self):
        from ai_agent.qgis_tools.processing.search_processing import SearchProcessingTool

        first = _Searchable("model:audit", "Audit buffer")
        registry = _Registry([first])
        with mock.patch.object(utils, "get_registry", return_value=registry):
            found = SearchProcessingTool().execute({"query": "audit buffer"})
            self.assertEqual([item["id"] for item in found["algorithms"]], ["model:audit"])
            first.deleted = True
            registry.current = [_Searchable("model:audit", "Audit buffer v2")]
            found = SearchProcessingTool().execute({"query": "audit buffer"})
        self.assertEqual([item["name"] for item in found["algorithms"]], ["Audit buffer v2"])


class _Parsed:
    def __init__(self, text):
        self._text = text

    def referencedFunctions(self):
        return {name for name in ("env", "eval", "upper") if f"{name}(" in self._text}


class _Calculator:
    @staticmethod
    def id():
        return "native:fieldcalculator"

    @staticmethod
    def parameterDefinitions():
        return [
            _Parameter("FORMULA", "expression"),
            _Parameter("FIELDS_MAPPING", "fields_mapping"),
            _Parameter("AGGREGATES", "aggregates"),
            _Parameter("FIELD_NAME", "string"),
        ]


class ExpressionParameterTest(unittest.TestCase):
    def test_every_expression_a_run_evaluates_is_found(self):
        arguments = {
            "FORMULA": "upper(name)",
            "FIELDS_MAPPING": [{"name": "a", "expression": "eval('1')"}, {"name": "b"}],
            "AGGREGATES": [{"aggregate": "first_value", "input": "env('HOME')"}],
            "FIELD_NAME": "env('not an expression')",
        }
        self.assertEqual(
            utils.expression_texts(_Calculator(), arguments),
            [("FORMULA", "upper(name)"), ("FIELDS_MAPPING", "eval('1')"), ("AGGREGATES", "env('HOME')")],
        )

    def test_run_processing_refuses_an_unsafe_function_in_any_expression(self):
        from ai_agent.qgis_tools.common import expressions
        from ai_agent.qgis_tools.processing import run_processing

        tool = run_processing.RunProcessingTool()
        with (
            mock.patch.object(expressions, "QgsExpression", _Parsed),
            mock.patch.object(run_processing, "find_algorithm", return_value=_Calculator()),
            mock.patch.object(run_processing, "coerce_parameters", side_effect=lambda algorithm, arguments: arguments),
            mock.patch.object(run_processing, "check_distance_units"),
        ):
            for parameters in (
                {"FORMULA": "env('HOME')"},
                {"FIELDS_MAPPING": [{"name": "a", "expression": "eval('env(''HOME'')')"}]},
                {"AGGREGATES": [{"input": "env('HOME')"}]},
            ):
                arguments = {"algorithm_id": "native:fieldcalculator", "parameters": parameters}
                with self.subTest(parameters=parameters), self.assertRaisesRegex(ValueError, r"\(\) is not allowed in"):
                    tool.prepare(arguments)
                with self.subTest(parameters=parameters), self.assertRaisesRegex(ValueError, r"\(\) is not allowed in"):
                    tool.execute(arguments)
            safe = {"algorithm_id": "native:fieldcalculator", "parameters": {"FORMULA": "upper(name)"}}
            with mock.patch.object(run_processing, "destination_parameter_names", return_value=[]):
                self.assertEqual(tool.prepare(safe)["parameters"], {"FORMULA": "upper(name)"})


if __name__ == "__main__":
    unittest.main()
