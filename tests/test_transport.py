import json
import unittest

from ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from ai_agent.core.llm.turns import parse_json_turn, parse_native_turn


def native(content, calls):
    return {"choices": [{"finish_reason": "tool_calls", "message": {"content": content, "tool_calls": calls}}]}


def json_reply(content):
    return {"choices": [{"message": {"content": content}}]}


class NativeTurnTest(unittest.TestCase):
    def test_call_name_and_arguments(self):
        turn = parse_native_turn(
            native(
                None,
                [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "describe_layer", "arguments": '{"layer_name":"Города"}'},
                    }
                ],
            )
        )
        self.assertEqual(turn.tool_calls[0].name, "describe_layer")
        self.assertEqual(turn.tool_calls[0].arguments, {"layer_name": "Города"})
        self.assertEqual(turn.protocol, "native")

    def test_several_calls_keep_order(self):
        turn = parse_native_turn(
            native(
                None,
                [
                    {"id": "a", "function": {"name": "list_layers", "arguments": "{}"}},
                    {"id": "b", "function": {"name": "get_qgis_info", "arguments": "{}"}},
                ],
            )
        )
        self.assertEqual([call.name for call in turn.tool_calls], ["list_layers", "get_qgis_info"])

    def test_nameless_call_is_dropped(self):
        turn = parse_native_turn(native(None, [{"id": "a", "function": {"arguments": "{}"}}]))
        self.assertEqual(turn.tool_calls, [])

    def test_plain_answer_has_no_calls(self):
        turn = parse_native_turn(json_reply("готово"))
        self.assertEqual(turn.text, "готово")
        self.assertEqual(turn.tool_calls, [])

    def test_empty_choices_raise(self):
        with self.assertRaises(ValueError):
            parse_native_turn({"choices": []})


class JsonTurnTest(unittest.TestCase):
    def test_bare_object(self):
        turn = parse_json_turn(json_reply('{"text":"t","tool_calls":[{"name":"list_layers","arguments":{}}]}'))
        self.assertEqual(turn.tool_calls[0].name, "list_layers")
        self.assertEqual(turn.protocol, "json")

    def test_markdown_fence_is_stripped(self):
        turn = parse_json_turn(json_reply('```json\n{"text":"t","tool_calls":[]}\n```'))
        self.assertEqual(turn.text, "t")

    def test_a_fence_inside_the_answer_is_not_taken_for_the_reply(self):
        reply = json.dumps({"text": 'Use this:\n```\n"population" > 1000\n```', "tool_calls": []})
        self.assertIn("population", parse_json_turn(json_reply(reply)).text)

    def test_a_call_in_the_native_shape_is_read(self):
        reply = '{"tool_calls":[{"function":{"name":"list_layers","arguments":"{}"}}]}'
        self.assertEqual([call.name for call in parse_json_turn(json_reply(reply)).tool_calls], ["list_layers"])

    def test_text_that_is_not_a_string_does_not_crash(self):
        self.assertEqual(parse_json_turn(json_reply('{"text": ["a", "b"]}')).text, "a\nb")
        self.assertEqual(parse_json_turn(json_reply('{"text": 5}')).text, "5")

    def test_broken_arguments_are_not_replaced_by_a_nested_object(self):
        self.assertEqual(parse_tool_arguments('{"layer": "roads", "style": {"color": "red"}, }'), {})
        self.assertEqual(parse_tool_arguments('Arguments: {"layer": "roads"}'), {"layer": "roads"})

    def test_prose_is_treated_as_final_answer(self):
        turn = parse_json_turn(json_reply("просто текст"))
        self.assertEqual(turn.text, "просто текст")
        self.assertEqual(turn.tool_calls, [])

    def test_the_finish_reason_is_kept_whatever_the_reply_holds(self):
        for content in ("", "plain prose", '{"text": "t", "tool_calls": []}'):
            with self.subTest(content=content):
                data = {"choices": [{"message": {"content": content}, "finish_reason": "length"}]}
                self.assertEqual(parse_json_turn(data).finish_reason, "length")

    def test_params_key_is_accepted(self):
        turn = parse_json_turn(json_reply('{"tool_calls":[{"tool":"list_layers","params":{"a":1}}]}'))
        self.assertEqual(turn.tool_calls[0].arguments, {"a": 1})


class ParserTest(unittest.TestCase):
    def test_object_after_prose(self):
        self.assertEqual(parse_model_json('бла бла {"text":"x"}')["text"], "x")

    def test_richest_object_wins(self):
        parsed = parse_model_json('{"a":1} {"text":"x","tool_calls":[]}')
        self.assertIn("tool_calls", parsed)

    def test_arguments_as_object(self):
        self.assertEqual(parse_tool_arguments({"a": 1}), {"a": 1})

    def test_arguments_as_string(self):
        self.assertEqual(parse_tool_arguments('{"a":1}'), {"a": 1})

    def test_broken_arguments_give_empty(self):
        self.assertEqual(parse_tool_arguments("не json"), {})

    def test_empty_arguments(self):
        self.assertEqual(parse_tool_arguments(""), {})


if __name__ == "__main__":
    unittest.main()
