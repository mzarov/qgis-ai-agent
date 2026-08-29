import unittest

from ai_agent.core.agent.transcript import ToolResult, Transcript
from ai_agent.core.llm import anthropic
from ai_agent.core.llm.client import build_request
from ai_agent.core.llm.dialects import ANTHROPIC, OPENAI, detect, headers_for, resolve
from ai_agent.core.llm.transport import PROTOCOL_NATIVE, ModelTurn, ToolCall

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_layers",
        "description": "Список слоёв",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
}


class DetectTest(unittest.TestCase):
    def test_anthropic_host_is_recognised(self):
        self.assertEqual(detect("https://api.anthropic.com/v1"), ANTHROPIC)

    def test_everything_else_is_openai_shaped(self):
        for url in (
            "https://openrouter.ai/api/v1",
            "https://api.deepseek.com/v1",
            "https://api.openai.com/v1",
            "http://localhost:11434/v1",
        ):
            self.assertEqual(detect(url), OPENAI, url)

    def test_lookalike_host_is_not_anthropic(self):
        self.assertEqual(detect("https://api.anthropic.com.evil.net/v1"), OPENAI)

    def test_explicit_choice_beats_detection(self):
        self.assertEqual(resolve("https://openrouter.ai/api/v1", ANTHROPIC), ANTHROPIC)
        self.assertEqual(resolve("https://api.anthropic.com/v1", OPENAI), OPENAI)

    def test_auto_falls_back_to_detection(self):
        self.assertEqual(resolve("https://api.anthropic.com/v1", "auto"), ANTHROPIC)
        self.assertEqual(resolve("https://api.anthropic.com/v1", ""), ANTHROPIC)


class HeaderTest(unittest.TestCase):
    def test_anthropic_uses_its_own_auth_header(self):
        headers = headers_for(ANTHROPIC, "ключ", "Bearer", "https://api.anthropic.com/v1")
        self.assertEqual(headers["x-api-key"], "ключ")
        self.assertIn("anthropic-version", headers)
        self.assertNotIn("Authorization", headers)

    def test_openai_uses_bearer(self):
        headers = headers_for(OPENAI, "ключ", "Bearer", "https://api.openai.com/v1")
        self.assertEqual(headers["Authorization"], "Bearer ключ")

    def test_openrouter_gets_attribution_headers(self):
        headers = headers_for(OPENAI, "ключ", "Bearer", "https://openrouter.ai/api/v1")
        self.assertIn("HTTP-Referer", headers)
        self.assertIn("X-Title", headers)

    def test_other_providers_get_no_extra_headers(self):
        headers = headers_for(OPENAI, "ключ", "Bearer", "https://api.deepseek.com/v1")
        self.assertNotIn("HTTP-Referer", headers)


class EndpointTest(unittest.TestCase):
    def _endpoint(self, url, dialect="auto"):
        endpoint, _, _ = build_request(
            url_override=url,
            key_override="ключ",
            auth_type_override="Bearer",
            model_override="демо",
            dialect_override=dialect,
        )
        return endpoint

    def test_anthropic_posts_to_messages(self):
        self.assertTrue(self._endpoint("https://api.anthropic.com/v1").endswith("/v1/messages"))

    def test_openai_posts_to_chat_completions(self):
        self.assertTrue(self._endpoint("https://openrouter.ai/api/v1").endswith("/v1/chat/completions"))


class TranslateTest(unittest.TestCase):
    def test_system_leaves_the_message_list(self):
        system, turns = anthropic.split_system(
            [{"role": "system", "content": "правила"}, {"role": "user", "content": "привет"}]
        )
        self.assertEqual(system, "правила")
        self.assertEqual(turns, [{"role": "user", "content": "привет"}])

    def test_several_system_messages_are_joined(self):
        system, _ = anthropic.split_system([{"role": "system", "content": "раз"}, {"role": "system", "content": "два"}])
        self.assertEqual(system, "раз\n\nдва")

    def test_tool_calls_become_tool_use_blocks(self):
        _, turns = anthropic.split_system(
            [
                {
                    "role": "assistant",
                    "content": "смотрю",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "list_layers", "arguments": '{"limit": 5}'},
                        }
                    ],
                }
            ]
        )
        blocks = turns[0]["content"]
        self.assertEqual(blocks[0], {"type": "text", "text": "смотрю"})
        self.assertEqual(blocks[1]["type"], "tool_use")
        self.assertEqual(blocks[1]["name"], "list_layers")
        self.assertEqual(blocks[1]["input"], {"limit": 5})

    def test_tool_results_become_a_user_message(self):
        _, turns = anthropic.split_system([{"role": "tool", "tool_call_id": "c1", "content": '{"слоёв": 3}'}])
        self.assertEqual(turns[0]["role"], "user")
        block = turns[0]["content"][0]
        self.assertEqual(block["type"], "tool_result")
        self.assertEqual(block["tool_use_id"], "c1")

    def test_neighbouring_user_messages_are_merged(self):
        _, turns = anthropic.split_system(
            [
                {"role": "tool", "tool_call_id": "c1", "content": "раз"},
                {"role": "tool", "tool_call_id": "c2", "content": "два"},
            ]
        )
        self.assertEqual(len(turns), 1)
        self.assertEqual(len(turns[0]["content"]), 2)

    def test_assistant_without_content_is_dropped(self):
        _, turns = anthropic.split_system([{"role": "assistant", "content": ""}])
        self.assertEqual(turns, [])

    def test_tool_schema_is_reshaped(self):
        translated = anthropic.translate_tool(TOOL_SCHEMA)
        self.assertEqual(translated["name"], "list_layers")
        self.assertIn("input_schema", translated)
        self.assertNotIn("parameters", translated)

    def test_body_carries_max_tokens_and_system(self):
        body = anthropic.build_body(
            [{"role": "system", "content": "правила"}, {"role": "user", "content": "привет"}],
            [TOOL_SCHEMA],
            "claude-demo",
        )
        self.assertEqual(body["model"], "claude-demo")
        self.assertGreater(body["max_tokens"], 0)
        self.assertEqual(body["system"], "правила")
        self.assertEqual(body["tools"][0]["name"], "list_layers")
        self.assertNotIn("stream", body)

    def test_body_without_tools_omits_the_key(self):
        body = anthropic.build_body([{"role": "user", "content": "привет"}], [], "claude-demo")
        self.assertNotIn("tools", body)


class ParseTest(unittest.TestCase):
    def test_text_and_tool_use_are_split(self):
        text, calls, stop = anthropic.parse_response(
            {
                "content": [
                    {"type": "text", "text": "сейчас посмотрю"},
                    {"type": "tool_use", "id": "t1", "name": "list_layers", "input": {"limit": 5}},
                ],
                "stop_reason": "tool_use",
            }
        )
        self.assertEqual(text, "сейчас посмотрю")
        self.assertEqual(calls[0]["name"], "list_layers")
        self.assertEqual(calls[0]["input"], {"limit": 5})
        self.assertEqual(stop, "tool_use")

    def test_plain_answer_has_no_calls(self):
        text, calls, stop = anthropic.parse_response(
            {"content": [{"type": "text", "text": "готово"}], "stop_reason": "end_turn"}
        )
        self.assertEqual((text, calls, stop), ("готово", [], "end_turn"))

    def test_empty_response_does_not_explode(self):
        self.assertEqual(anthropic.parse_response({}), ("", [], ""))

    def test_unknown_blocks_are_ignored(self):
        text, calls, _ = anthropic.parse_response({"content": [{"type": "thinking", "text": "…"}, "мусор"]})
        self.assertEqual((text, calls), ("", []))


class WholeTranscriptTest(unittest.TestCase):
    def setUp(self):
        call = ToolCall(id="c1", name="list_layers", arguments={"limit": 5})
        transcript = Transcript()
        transcript.add_user("какие у меня слои?")
        transcript.add_turn(ModelTurn(text="смотрю", tool_calls=[call], protocol=PROTOCOL_NATIVE))
        transcript.add_results([ToolResult(call=call, payload={"layers": ["Дороги"]})], PROTOCOL_NATIVE)
        self.body = anthropic.build_body(transcript.build_messages("Ты агент QGIS."), [TOOL_SCHEMA], "claude-demo")

    def test_system_prompt_moves_out_of_the_list(self):
        self.assertEqual(self.body["system"], "Ты агент QGIS.")
        self.assertTrue(all(turn["role"] != "system" for turn in self.body["messages"]))

    def test_roles_alternate_as_anthropic_requires(self):
        roles = [turn["role"] for turn in self.body["messages"]]
        self.assertEqual(roles, ["user", "assistant", "user"])

    def test_the_call_and_its_result_keep_the_same_id(self):
        turns = self.body["messages"]
        used = next(b for b in turns[1]["content"] if b["type"] == "tool_use")
        result = turns[2]["content"][0]
        self.assertEqual(used["id"], result["tool_use_id"])

    def test_round_trip_survives_a_second_turn(self):
        text, calls, _ = anthropic.parse_response(
            {"content": [{"type": "tool_use", "id": "c2", "name": "describe_layer", "input": {}}]}
        )
        self.assertEqual(calls[0]["name"], "describe_layer")
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
