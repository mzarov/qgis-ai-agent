import json
import unittest

from qgis_ai_agent.core.agent.transcript import ToolResult, Transcript
from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall


def call(name="list_layers"):
    return ToolCall(id="c1", name=name, arguments={"a": 1})


class NativeRenderingTest(unittest.TestCase):
    def setUp(self):
        self.turn = ModelTurn(text="", tool_calls=[call()], protocol="native")

    def test_roles_sequence(self):
        transcript = Transcript()
        transcript.add_user("вопрос")
        transcript.add_turn(self.turn)
        transcript.add_results([ToolResult(call=call(), payload={"ok": 1})], "native")
        roles = [message["role"] for message in transcript.build_messages("S")]
        self.assertEqual(roles, ["system", "user", "assistant", "tool"])

    def test_tool_call_is_serialised(self):
        transcript = Transcript()
        transcript.add_turn(self.turn)
        message = transcript.build_messages("S")[1]
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "list_layers")
        self.assertEqual(json.loads(message["tool_calls"][0]["function"]["arguments"]), {"a": 1})

    def test_result_carries_call_id(self):
        transcript = Transcript()
        transcript.add_results([ToolResult(call=call(), payload={})], "native")
        self.assertEqual(transcript.build_messages("S")[1]["tool_call_id"], "c1")

    def test_history_sits_between_system_and_run(self):
        transcript = Transcript()
        transcript.add_user("вопрос")
        roles = [m["role"] for m in transcript.build_messages("S", [{"role": "user", "content": "раньше"}])]
        self.assertEqual(roles, ["system", "user", "user"])


class JsonRenderingTest(unittest.TestCase):
    def test_results_come_back_as_user_message(self):
        transcript = Transcript()
        transcript.add_turn(ModelTurn(text="t", tool_calls=[call()], protocol="json"))
        transcript.add_results([ToolResult(call=call(), payload={})], "json")
        roles = [message["role"] for message in transcript.build_messages("S")]
        self.assertEqual(roles, ["system", "assistant", "user"])


class ToolResultTest(unittest.TestCase):
    def test_failure_keeps_arguments(self):
        result = ToolResult.failure(call(), "боль")
        self.assertFalse(result.ok)
        self.assertEqual(result.payload["error"], "боль")
        self.assertEqual(result.payload["arguments_sent"], {"a": 1})

    def test_long_payload_is_truncated(self):
        result = ToolResult(call=call(), payload={"x": "д" * 9000})
        self.assertIn("обрезан", result.to_text())

    def test_unserialisable_payload_does_not_raise(self):
        ToolResult(call=call(), payload={"x": object()}).to_text()


if __name__ == "__main__":
    unittest.main()
