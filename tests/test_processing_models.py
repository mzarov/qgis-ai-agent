import json
import os
import tempfile
import unittest
from unittest import mock

from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_READ, SAFETY_WRITE
from ai_agent.qgis_tools.processing import list_processing_history as history_module
from ai_agent.qgis_tools.processing import model_builder
from ai_agent.qgis_tools.processing.model_spec import (
    InputSource,
    StaticSource,
    StepSource,
    parse_model,
)
from ai_agent.qgis_tools.registry import get_tool_by_name


def two_steps(**overrides):
    params = {
        "name": "Buffer in UTM",
        "group": "Agent",
        "inputs": [
            {"name": "points", "type": "vector"},
            {"name": "target_crs", "type": "crs", "default": "EPSG:32637"},
            {"name": "distance", "type": "distance", "default": "500"},
        ],
        "steps": [
            {
                "id": "reproject",
                "algorithm_id": "native:reprojectlayer",
                "parameters": {"INPUT": {"input": "points"}, "TARGET_CRS": {"input": "target_crs"}},
            },
            {
                "id": "buffer",
                "algorithm_id": "native:buffer",
                "parameters": {
                    "INPUT": {"step": "reproject", "output": "OUTPUT"},
                    "DISTANCE": {"input": "distance"},
                    "DISSOLVE": False,
                    "OUTPUT": "TEMPORARY_OUTPUT",
                },
            },
        ],
        "outputs": [{"name": "Buffered", "step": "buffer"}],
    }
    params.update(overrides)
    return params


class ModelSpecTest(unittest.TestCase):
    def test_a_two_step_chain_resolves_inputs_earlier_steps_and_values(self):
        spec = parse_model(two_steps())
        self.assertEqual(spec.name, "Buffer in UTM")
        reproject, buffer = spec.steps
        self.assertEqual(reproject.sources["INPUT"], InputSource("points"))
        self.assertEqual(buffer.sources["INPUT"], StepSource("reproject", "OUTPUT"))
        self.assertEqual(buffer.sources["DISSOLVE"], StaticSource(False))
        self.assertEqual(spec.outputs[0].output, "OUTPUT", "the output defaults to OUTPUT")
        self.assertEqual(spec.inputs[2].default, 500.0)

    def test_a_distance_takes_its_units_from_the_one_crs_input_never_from_a_layer_by_default(self):
        spec = parse_model(two_steps())
        self.assertEqual(spec.inputs[2].parent, "target_crs")
        without_crs = two_steps()
        without_crs["inputs"] = [{"name": "points", "type": "vector"}, {"name": "distance", "type": "distance"}]
        without_crs["steps"] = [
            {
                "id": "buffer",
                "algorithm_id": "native:buffer",
                "parameters": {"INPUT": {"input": "points"}, "DISTANCE": {"input": "distance"}},
            }
        ]
        self.assertEqual(parse_model(without_crs).inputs[1].parent, "", "a reprojecting model would show degrees")

    def test_a_field_lists_the_fields_of_the_only_vector_input(self):
        params = two_steps()
        params["inputs"].append({"name": "field", "type": "field"})
        params["steps"][1]["parameters"]["FIELD"] = {"input": "field"}
        self.assertEqual(parse_model(params).inputs[-1].parent, "points")
        params["inputs"].append({"name": "other", "type": "vector"})
        params["steps"][1]["parameters"]["OTHER"] = {"input": "other"}
        with self.assertRaisesRegex(ValueError, "needs parent"):
            parse_model(params)

    def test_an_unknown_step_is_refused_with_the_steps_before_it(self):
        params = two_steps()
        params["steps"][1]["parameters"]["INPUT"] = {"step": "clip"}
        with self.assertRaisesRegex(ValueError, "unknown step 'clip'. Steps before it: reproject"):
            parse_model(params)

    def test_an_unknown_input_is_refused_with_the_declared_ones(self):
        params = two_steps()
        params["steps"][0]["parameters"]["INPUT"] = {"input": "layer"}
        with self.assertRaisesRegex(ValueError, "unknown input 'layer'. Declared inputs: points, target_crs"):
            parse_model(params)

    def test_a_forward_reference_is_refused_so_no_cycle_can_be_written(self):
        params = two_steps()
        params["steps"][0]["parameters"]["INPUT"] = {"step": "buffer", "output": "OUTPUT"}
        with self.assertRaisesRegex(ValueError, "which comes later"):
            parse_model(params)

    def test_a_step_cannot_feed_itself(self):
        params = two_steps()
        params["steps"][1]["parameters"]["INPUT"] = {"step": "buffer"}
        with self.assertRaisesRegex(ValueError, "its own step"):
            parse_model(params)

    def test_a_bad_input_type_is_refused_with_the_supported_ones(self):
        params = two_steps()
        params["inputs"][0]["type"] = "layer"
        with self.assertRaisesRegex(ValueError, "Use one of: vector, raster, number, distance, field, string, crs"):
            parse_model(params)

    def test_bad_names_ids_and_defaults_are_refused(self):
        cases = {
            "name": ({"name": "a/b"}, "file name"),
            "input name": ({"inputs": [{"name": "my layer", "type": "vector"}]}, "not usable as a parameter name"),
            "duplicate step": (
                {
                    "steps": [
                        {"id": "a", "algorithm_id": "native:buffer"},
                        {"id": "a", "algorithm_id": "native:buffer"},
                    ],
                    "inputs": [],
                    "outputs": [{"name": "x", "step": "a"}],
                },
                "Two steps have the id 'a'",
            ),
            "default": ({"inputs": [{"name": "d", "type": "number", "default": "far"}]}, "must be a number"),
            "no steps": ({"steps": []}, "at least one entry in steps"),
        }
        for label, (override, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                parse_model(two_steps(**override))

    def test_an_unused_input_is_refused(self):
        params = two_steps()
        params["inputs"].append({"name": "spare", "type": "number"})
        with self.assertRaisesRegex(ValueError, "Input 'spare' is never used"):
            parse_model(params)

    def test_outputs_name_a_real_step_and_never_clash(self):
        cases = {
            "unknown step": ([{"name": "Result", "step": "clip"}], "not a step"),
            "clash with an input": ([{"name": "Points", "step": "buffer"}], "clashes"),
            "twice": (
                [{"name": "A", "step": "buffer"}, {"name": "B", "step": "buffer"}],
                "already the output 'A'",
            ),
        }
        for label, (outputs, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                parse_model(two_steps(outputs=outputs))

    def test_a_reference_holds_nothing_else(self):
        params = two_steps()
        params["steps"][1]["parameters"]["INPUT"] = {"step": "reproject", "input": "points"}
        with self.assertRaisesRegex(ValueError, "nothing else in the same object"):
            parse_model(params)


class _Definition:
    def __init__(self, name, kind="number", destination=False, options=None):
        self._name, self._kind, self._destination, self._options = name, kind, destination, options or []

    def name(self):
        return self._name

    def type(self):
        return self._kind

    def isDestination(self):
        return self._destination

    def options(self):
        return self._options


class _Named:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _Algorithm:
    def __init__(self, identifier, definitions, outputs=("OUTPUT",)):
        self._id, self._definitions, self._outputs = identifier, definitions, outputs

    def id(self):
        return self._id

    def parameterDefinitions(self):
        return self._definitions

    def outputDefinitions(self):
        return [_Named(name) for name in self._outputs]


ALGORITHMS = {
    "native:reprojectlayer": _Algorithm(
        "native:reprojectlayer",
        [_Definition("INPUT", "source"), _Definition("TARGET_CRS", "crs"), _Definition("OUTPUT", "sink", True)],
    ),
    "native:buffer": _Algorithm(
        "native:buffer",
        [
            _Definition("INPUT", "source"),
            _Definition("DISTANCE", "distance"),
            _Definition("END_CAP_STYLE", "enum", options=["Round", "Flat", "Square"]),
            _Definition("DISSOLVE", "boolean"),
            _Definition("OUTPUT", "sink", True),
        ],
    ),
}


class _Layer:
    @staticmethod
    def name():
        return "stations"


def _find(identifier):
    if identifier not in ALGORITHMS:
        raise ValueError(f"Algorithm not found: {identifier}. Look the exact identifier up with search_processing.")
    return ALGORITHMS[identifier]


class RegistryCheckTest(unittest.TestCase):
    def setUp(self):
        for name, value in (("find_algorithm", _find), ("resolve_layer", lambda value: None)):
            patcher = mock.patch.object(model_builder, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def checked(self, params):
        return model_builder.checked_against_registry(parse_model(params))

    def test_a_temporary_output_is_dropped_and_enum_labels_become_indexes(self):
        params = two_steps()
        params["steps"][1]["parameters"]["END_CAP_STYLE"] = "flat"
        buffer = self.checked(params).steps[1]
        self.assertNotIn("OUTPUT", buffer.sources)
        self.assertEqual(buffer.sources["END_CAP_STYLE"], StaticSource(1))

    def test_an_unknown_algorithm_names_the_step(self):
        params = two_steps()
        params["steps"][0]["algorithm_id"] = "native:reproject"
        with self.assertRaisesRegex(ValueError, "Step 'reproject': Algorithm not found: native:reproject"):
            self.checked(params)

    def test_an_unknown_parameter_lists_the_real_ones(self):
        params = two_steps()
        params["steps"][1]["parameters"]["RADIUS"] = 5
        with self.assertRaisesRegex(ValueError, "has no parameter RADIUS. Its parameters: INPUT, DISTANCE"):
            self.checked(params)

    def test_an_output_path_inside_a_step_is_refused(self):
        params = two_steps()
        params["steps"][1]["parameters"]["OUTPUT"] = "/data/buffer.gpkg"
        with self.assertRaisesRegex(ValueError, "Leave it out"):
            self.checked(params)

    def test_a_step_output_and_a_model_output_must_exist(self):
        params = two_steps()
        params["steps"][1]["parameters"]["INPUT"] = {"step": "reproject", "output": "RESULT"}
        with self.assertRaisesRegex(ValueError, "has no such output. Its outputs: OUTPUT"):
            self.checked(params)
        with self.assertRaisesRegex(ValueError, "not one of its outputs. Use one of: OUTPUT"):
            self.checked(two_steps(outputs=[{"name": "Buffered", "step": "buffer", "output": "DISTANCE"}]))

    def test_a_project_layer_or_scratch_layer_as_a_fixed_value_is_refused(self):
        params = two_steps()
        params["inputs"] = params["inputs"][1:]
        params["steps"][0]["parameters"]["INPUT"] = "stations"
        with (
            mock.patch.object(model_builder, "resolve_layer", lambda value: _Layer()),
            self.assertRaisesRegex(ValueError, "names layer 'stations' of this project"),
        ):
            self.checked(params)
        params["steps"][0]["parameters"]["INPUT"] = "memory://Point?crs=EPSG:4326&uid={1}"
        with self.assertRaisesRegex(ValueError, "a scratch layer"):
            self.checked(params)
        params["steps"][0]["parameters"]["INPUT"] = "/data/stations.gpkg"
        self.assertEqual(self.checked(params).steps[0].sources["INPUT"], StaticSource("/data/stations.gpkg"))


class _Loaded:
    def __init__(self, path):
        self._path = path

    def sourceFilePath(self):
        return self._path


class ModelTargetTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "Buffer in UTM.model3")

    def test_an_existing_file_needs_overwrite_and_a_model_from_elsewhere_is_never_shadowed(self):
        with mock.patch.object(model_builder, "registered_model", return_value=None):
            model_builder.check_target("model:Buffer in UTM", self.path, False)
            with open(self.path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            with self.assertRaisesRegex(ValueError, "already exists"):
                model_builder.check_target("model:Buffer in UTM", self.path, False)
            model_builder.check_target("model:Buffer in UTM", self.path, True)
        elsewhere = _Loaded("/other/Buffer in UTM.model3")
        with (
            mock.patch.object(model_builder, "registered_model", return_value=elsewhere),
            self.assertRaisesRegex(ValueError, "already loaded from '/other/Buffer in UTM.model3'"),
        ):
            model_builder.check_target("model:Buffer in UTM", self.path, True)
        with mock.patch.object(model_builder, "registered_model", return_value=_Loaded(self.path)):
            model_builder.check_target("model:Buffer in UTM", self.path, True)


class CreateToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = get_tool_by_name("create_processing_model")

    def test_it_is_a_queued_write_with_an_external_effect_and_overwrite_is_destructive(self):
        self.assertEqual(self.tool.safety, SAFETY_WRITE)
        self.assertTrue(self.tool.has_external_effect({}))
        self.assertEqual(self.tool.safety_for({"overwrite": True}), SAFETY_DESTRUCTIVE)
        self.assertEqual(self.tool.safety_for({}), SAFETY_WRITE)

    def test_summaries_survive_malformed_arguments(self):
        for params in ({}, {"name": 5, "steps": "x"}, {"name": "M", "steps": [1, {"id": "a"}], "inputs": "x"}):
            with self.subTest(params=params):
                self.assertTrue(self.tool.summarize_call(params))
                self.assertTrue(self.tool.detail_call(params))
        summary = self.tool.summarize_call(two_steps())
        self.assertIn("Buffer in UTM", summary)
        self.assertIn("2 steps", summary)
        detail = self.tool.detail_call({**two_steps(), "_path": "/models/Buffer in UTM.model3"})
        self.assertIn("2. buffer — native:buffer", detail)
        self.assertIn("/models/Buffer in UTM.model3", detail)

    def test_a_missing_file_is_not_confirmed(self):
        payload = {"algorithm_id": "model:Gone", "path": "/nowhere/Gone.model3"}
        self.assertFalse(self.tool.confirm_applied({}, payload))
        self.assertEqual(self.tool.summarize_result({}, payload), "In the Toolbox as model:Gone")


class _Entry:
    def __init__(self, identifier, details):
        self.id = identifier
        self.entry = details
        self.timestamp = f"2026-10-16T10:0{identifier}:00"


class _History:
    def __init__(self, entries):
        self.entries = entries
        self.asked = None

    def queryEntries(self, start, end, provider):
        self.asked = provider
        return list(self.entries)


class _Gui:
    registry = None

    @classmethod
    def historyProviderRegistry(cls):
        return cls.registry


BUFFER_RUN = {
    "algorithm_id": "native:buffer",
    "parameters": {
        "ellipsoid": "EPSG:7030",
        "inputs": {"INPUT": "memory://Point?uid={7}", "DISTANCE": 500, "OUTPUT": "TEMPORARY_OUTPUT"},
    },
    "results": {"OUTPUT": "Buffered_1", "CHILD_RESULTS": {"x": 1}},
}


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tool = get_tool_by_name("list_processing_history")
        patcher = mock.patch.object(history_module, "QgsGui", _Gui)
        patcher.start()
        self.addCleanup(patcher.stop)
        names = {"memory://Point?uid={7}": "stations", "Buffered_1": "Buffered"}
        layers = mock.patch.object(history_module, "project_layer_names", return_value=names)
        layers.start()
        self.addCleanup(layers.stop)

    def test_it_is_a_local_read(self):
        self.assertEqual(self.tool.safety, SAFETY_READ)
        self.assertFalse(self.tool.has_network_access({}))

    def test_an_entry_shows_its_inputs_and_names_the_project_layers_on_both_ends(self):
        layers = {"memory://Point?uid={7}": "stations", "Buffered_1": "Buffered"}
        shaped = history_module.history_entry(BUFFER_RUN, "2026-10-16T10:00:00", layers)
        self.assertEqual(
            shaped["parameters"], {"INPUT": "memory://Point?uid={7}", "DISTANCE": 500, "OUTPUT": "TEMPORARY_OUTPUT"}
        )
        self.assertEqual(shaped["project_layers"], {"INPUT": "stations"})
        self.assertEqual(shaped["results"], {"OUTPUT": "Buffered_1"}, "a model run's child results are noise")
        self.assertEqual(shaped["result_layers"], {"OUTPUT": "Buffered"})
        self.assertTrue(shaped["finished"])
        unfinished = history_module.history_entry({"algorithm_id": "native:clip", "parameters": {}}, "", {})
        self.assertFalse(unfinished["finished"])

    def test_long_values_are_shortened(self):
        self.assertTrue(history_module.shorten("x" * 1000).endswith("…"))
        self.assertLessEqual(len(history_module.shorten("x" * 1000)), history_module.MAX_VALUE_CHARS)
        self.assertEqual(len(history_module.shorten(list(range(50)))), history_module.MAX_LIST_ITEMS + 1)
        self.assertEqual(history_module.shorten(object.__new__(_Named))[:1], "<")

    def test_secrets_inside_json_values_and_secret_named_parameters_are_hidden(self):
        data = {
            "user": "me",
            "password": "hunter2",  # pragma: allowlist secret
            "list": [{"api_key": "k-123"}],  # pragma: allowlist secret
            "deep": {"x": {"token": "t-9"}},
        }
        run = {
            "algorithm_id": "native:httprequest",
            "parameters": {
                "inputs": {
                    "URL": "https://api.example/login",
                    "DATA": " " + json.dumps(data),
                    "PASSWORD": "pg-secret",  # pragma: allowlist secret
                    "HEADERS": {"Authorization": "Bearer xyz", "deep": {"deeper": {"token": "t-1"}}},
                }
            },
            "results": {"OUTPUT": '{"session": {"refresh_token": "r-7"}}'},
        }
        shaped = history_module.history_entry(run, "", {})
        shown = json.dumps(shaped)
        for secret in ("hunter2", "k-123", "t-9", "pg-secret", "xyz", "t-1", "r-7"):
            self.assertNotIn(secret, shown)
        self.assertEqual(json.loads(shaped["parameters"]["DATA"])["user"], "me")
        self.assertEqual(json.loads(shaped["parameters"]["DATA"])["password"], "<hidden>")
        self.assertEqual(shaped["parameters"]["PASSWORD"], "<hidden>")
        self.assertEqual(history_module.shorten("[not json"), "[not json")

    def test_the_latest_runs_come_oldest_first_within_the_limit(self):
        entries = [_Entry(index, {**BUFFER_RUN, "algorithm_id": f"native:step{index}"}) for index in (3, 1, 2)]
        _Gui.registry = _History(entries)
        payload = self.tool.execute({"limit": 2})
        self.assertEqual(_Gui.registry.asked, "processing")
        self.assertEqual([entry["algorithm_id"] for entry in payload["entries"]], ["native:step2", "native:step3"])
        self.assertEqual(payload["total_recent"], 3)
        self.assertEqual(self.tool.summarize_result({}, payload), "2 runs")

    def test_no_history_registry_is_said_plainly(self):
        _Gui.registry = None
        payload = self.tool.execute({})
        self.assertFalse(payload["available"])
        self.assertIn("run_processing calls of this conversation", payload["note"])
        self.assertEqual(self.tool.summarize_result({}, payload), "History unavailable")


if __name__ == "__main__":
    unittest.main()
