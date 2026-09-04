import unittest
from unittest import mock

from ai_agent.core.agent import executor as executor_module
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ModelTurn, ToolCall
from ai_agent.qgis_tools.base import RESULT_IMAGE_KEY
from ai_agent.qgis_tools.common.validation import validate_parameters
from ai_agent.qgis_tools.registry import ALL_TOOLS, execute_tool, get_tool_by_name, prepare_tool_call


class ToolArgumentValidationTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.loop._overrides = {"url_override": "http://localhost:11434/v1"}

    def test_wrong_declared_parameter_types_never_reach_execution_or_the_queue(self):
        invalid = {
            "string": 123,
            "number": {"value": 1},
            "integer": [1],
            "boolean": "false",
            "array": "not-an-array",
            "object": [],
        }
        with mock.patch.object(self.loop._executor, "run") as execute:
            for tool in ALL_TOOLS:
                for parameter in tool.params_schema:
                    name = parameter["name"]
                    kind = parameter.get("type", "string")
                    with self.subTest(tool=tool.name, parameter=name):
                        call = ToolCall(id="malformed", name=tool.name, arguments={name: invalid[kind]})
                        result = self.loop._dispatch(call)
                        self.assertFalse(result.ok)
                        self.assertIn(f"Parameter '{name}'", result.payload["error"])
                        self.assertFalse(self.loop.has_pending_writes)
            execute.assert_not_called()

    def test_non_object_arguments_fail_for_tools_and_control_calls(self):
        for name in ("save_project", "load_skill", "ask_user", "update_plan", "apply_now"):
            with self.subTest(tool=name):
                result = self.loop._dispatch(ToolCall(id="malformed", name=name, arguments=[]))
                self.assertFalse(result.ok)
                self.assertIn("must be an object", result.payload["error"])

    def test_policy_errors_are_returned_as_tool_results(self):
        tool = get_tool_by_name("save_project")
        with mock.patch.object(tool, "safety_for", side_effect=RuntimeError("policy failed")):
            result = self.loop._dispatch(ToolCall(id="policy", name=tool.name, arguments={}))
        self.assertFalse(result.ok)
        self.assertEqual(result.payload["error"], "policy failed")
        self.assertFalse(self.loop.has_pending_writes)

    def test_summary_error_does_not_replace_a_preparation_failure(self):
        tool = get_tool_by_name("set_symbol")
        with (
            mock.patch.object(tool, "prepare", side_effect=ValueError("preparation failed")),
            mock.patch.object(tool, "summarize_call", side_effect=RuntimeError("summary failed")),
        ):
            result = self.loop._dispatch(ToolCall(id="prepare", name=tool.name, arguments={}))
        self.assertFalse(result.ok)
        self.assertEqual(result.payload["error"], "preparation failed")
        self.assertFalse(self.loop.has_pending_writes)

    def test_malformed_call_does_not_stop_the_other_calls_or_next_turn(self):
        calls = [
            ToolCall(id="bad", name="save_project", arguments={"path": 123}),
            ToolCall(id="good", name="list_layers", arguments={}),
        ]
        with (
            mock.patch.object(self.loop._executor, "run", return_value=ToolResult(call=calls[1], payload={})) as run,
            mock.patch.object(self.loop, "_request_step") as next_step,
        ):
            self.loop._on_turn(ModelTurn(tool_calls=calls))
        run.assert_called_once_with(calls[1])
        next_step.assert_called_once_with()
        results = self.loop._transcript.entries[-1]["results"]
        self.assertEqual([result.ok for result in results], [False, True])

    def test_registry_entry_points_validate_before_calling_the_tool(self):
        tool = get_tool_by_name("save_project")
        with mock.patch.object(tool, "execute") as execute, mock.patch.object(tool, "prepare") as prepare:
            for entry in (execute_tool, prepare_tool_call):
                with self.subTest(entry=entry.__name__), self.assertRaisesRegex(ValueError, "Parameter 'path'"):
                    entry(tool.name, {"path": 123})
        execute.assert_not_called()
        prepare.assert_not_called()

    def test_numeric_strings_and_optional_defaults_remain_supported(self):
        params = {"limit": "10", "opacity": "0.25", "title": None, "legacy": "value"}
        schema = [
            {"name": "limit", "type": "integer"},
            {"name": "opacity", "type": "number"},
            {"name": "title", "type": "string"},
            {"name": "missing", "type": "string", "required": True},
        ]
        validate_parameters(params, schema)
        self.assertEqual(params["limit"], "10")
        self.assertEqual(params["opacity"], "0.25")

    def test_domain_specific_array_values_and_property_coercions_remain_supported(self):
        validate_parameters({"values": [1, 2, None]}, get_tool_by_name("set_categories").params_schema)
        validate_parameters(
            {"properties": {"size": "4", "enabled": "false"}}, get_tool_by_name("set_symbol").params_schema
        )


class ExecutorResultBoundaryTest(unittest.TestCase):
    def test_result_normalization_does_not_mutate_the_tool_payload(self):
        payload = {RESULT_IMAGE_KEY: "image", "width": 10}
        call = ToolCall(id="image", name="render_map", arguments={})
        with mock.patch.object(executor_module, "execute_tool", return_value=payload):
            result = executor_module.ToolExecutor().run(call)
        self.assertTrue(result.ok)
        self.assertEqual(result.image, "image")
        self.assertEqual(payload, {RESULT_IMAGE_KEY: "image", "width": 10})

    def test_result_conversion_failure_is_returned_as_a_tool_error(self):
        class BrokenImage:
            def __str__(self):
                raise ValueError("image conversion failed")

        call = ToolCall(id="image", name="render_map", arguments={})
        with mock.patch.object(executor_module, "execute_tool", return_value={RESULT_IMAGE_KEY: BrokenImage()}):
            result = executor_module.ToolExecutor().run(call)
        self.assertFalse(result.ok)
        self.assertEqual(result.payload["error"], "image conversion failed")
        self.assertEqual(result.egress, get_tool_by_name("render_map").egress)
