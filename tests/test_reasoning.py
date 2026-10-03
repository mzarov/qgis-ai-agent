import json
import unittest
from unittest import mock

from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.llm import transport
from ai_agent.core.llm.client import ApiResponseError
from ai_agent.core.llm.reasoning import REASONING_KEY, request_options, wire_messages
from ai_agent.core.llm.transport import ModelTurn, ToolCall, _openai_options

SCHEMAS = [{"type": "function", "function": {"name": "list_layers", "parameters": {}}}]
DEEPSEEK = "https://api.deepseek.com/v1"
OPENROUTER = "https://openrouter.ai/api/v1"
OPENAI = "https://api.openai.com/v1"
UNKNOWN = "https://llm.example.org/v1"
ANSWER = {"choices": [{"message": {"content": "done"}}]}
OPENAI_REFUSAL = json.dumps(
    {
        "error": {
            "message": "Unsupported parameter: 'reasoning_effort' is not supported with this model.",
            "type": "invalid_request_error",
            "param": "reasoning_effort",
            "code": "unsupported_parameter",
        }
    }
)


class ProviderBodyTest(unittest.TestCase):
    def test_deepseek_is_asked_to_think_with_its_own_switch(self):
        self.assertEqual(request_options(DEEPSEEK, True), {"thinking": {"type": "enabled"}})

    def test_deepseek_off_still_says_disabled_because_it_thinks_by_default(self):
        self.assertEqual(request_options(DEEPSEEK, False), {"thinking": {"type": "disabled"}})

    def test_openrouter_gets_its_unified_reasoning_object(self):
        self.assertEqual(request_options(OPENROUTER, True), {"reasoning": {"effort": "medium"}})

    def test_openai_gets_reasoning_effort(self):
        self.assertEqual(request_options(OPENAI, True), {"reasoning_effort": "medium"})

    def test_an_unknown_host_gets_the_openai_shape(self):
        self.assertEqual(request_options(UNKNOWN, True), {"reasoning_effort": "medium"})

    def test_off_sends_nothing_outside_deepseek(self):
        for url in (OPENROUTER, OPENAI, UNKNOWN):
            with self.subTest(url=url):
                self.assertEqual(request_options(url, False), {})

    def test_deepseek_with_tools_never_gets_tool_choice(self):
        options = _openai_options(DEEPSEEK, SCHEMAS, reasoning=True)
        self.assertEqual(options, {"tools": SCHEMAS, "thinking": {"type": "enabled"}})

    def test_other_hosts_keep_tool_choice_next_to_reasoning(self):
        options = _openai_options(OPENROUTER, SCHEMAS, reasoning=True)
        self.assertEqual(options["tool_choice"], "auto")
        self.assertEqual(options["reasoning"], {"effort": "medium"})


class WireMessagesTest(unittest.TestCase):
    MESSAGES = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "earlier answer from history"},
        {"role": "assistant", "content": None, "tool_calls": [], REASONING_KEY: "pondering"},
        {"role": "tool", "tool_call_id": "c1", "content": "{}"},
    ]

    def test_reasoning_never_reaches_other_providers(self):
        for url in (OPENAI, OPENROUTER, UNKNOWN):
            for enabled in (True, False):
                with self.subTest(url=url, enabled=enabled):
                    wired = json.dumps(wire_messages(self.MESSAGES, url, enabled))
                    self.assertNotIn("pondering", wired)
                    self.assertNotIn(REASONING_KEY, wired)

    def test_deepseek_without_reasoning_gets_nothing_back(self):
        wired = wire_messages(self.MESSAGES, DEEPSEEK, False)
        self.assertNotIn("reasoning_content", json.dumps(wired))

    def test_deepseek_thinking_gets_every_assistant_message_its_reasoning(self):
        wired = wire_messages(self.MESSAGES, DEEPSEEK, True)
        self.assertEqual(wired[2]["reasoning_content"], "pondering")
        self.assertEqual(wired[1]["reasoning_content"], "")
        self.assertNotIn("reasoning_content", wired[0])
        self.assertNotIn("reasoning_content", wired[3])
        self.assertNotIn(REASONING_KEY, json.dumps(wired))

    def test_the_input_is_left_untouched(self):
        wire_messages(self.MESSAGES, DEEPSEEK, True)
        self.assertEqual(self.MESSAGES[2][REASONING_KEY], "pondering")
        self.assertNotIn("reasoning_content", self.MESSAGES[1])

    def test_the_transcript_hands_a_native_turn_its_reasoning(self):
        transcript = Transcript()
        transcript.add_turn(ModelTurn(text="", thinking="pondering", tool_calls=[ToolCall("c1", "list_layers")]))
        self.assertEqual(transcript.build_messages("system")[-1][REASONING_KEY], "pondering")


class ReasoningDispatchTest(unittest.TestCase):
    """The switch, the refusal fallback and its memory, through the real openai dispatch."""

    def setUp(self):
        self.bodies: list[dict] = []
        self.supports_thinking: bool | None = None
        self.remembered: list[bool] = []
        self.replies: list = []
        patches = {
            "get_reasoning_enabled": lambda: True,
            "get_supports_thinking": lambda *scope: self.supports_thinking,
            "set_supports_thinking": self._remember,
            "get_supports_tools": lambda *scope: True,
            "set_supports_tools": lambda *args: self.fail("tools must not be switched off"),
            "get_supports_streaming": lambda *scope: True,
            "set_supports_streaming": lambda url, value, *scope: value or self.fail("streaming must stay on"),
            "post_chat_completion": self._post,
            "post_stream": self._stream,
            "build_request": lambda *args: ("https://x/chat/completions", {}, "model-x"),
            "get_dialect": lambda: "auto",
            "get_model": lambda: "model-x",
        }
        for name, value in patches.items():
            patcher = mock.patch.object(transport, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _remember(self, url, value, model=None, dialect=None):
        self.remembered.append(value)
        self.supports_thinking = value

    def _post(self, messages, extra_body=None, timeout=0, **overrides):
        body = {"messages": messages, **(extra_body or {})}
        self.bodies.append(body)
        reply = self.replies.pop(0) if self.replies else ANSWER
        if isinstance(reply, Exception):
            raise reply
        return reply

    def _stream(self, endpoint, headers, body, completion, timeout, verify=None, **options):
        return self._post(body["messages"], {key: value for key, value in body.items() if key != "messages"})

    def _call(self, url, on_chunk=None):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", REASONING_KEY: "pondering"},
            {"role": "user", "content": "go on"},
        ]
        return transport._dispatch(messages, SCHEMAS, {}, 10, url, on_chunk)

    def test_the_switch_puts_the_provider_parameter_on_the_wire(self):
        self._call(OPENROUTER)
        self.assertEqual(self.bodies[0]["reasoning"], {"effort": "medium"})
        self.assertNotIn("pondering", json.dumps(self.bodies[0]["messages"]))

    def test_the_switch_off_sends_nothing(self):
        with mock.patch.object(transport, "get_reasoning_enabled", lambda: False):
            self._call(OPENAI)
        self.assertNotIn("reasoning_effort", self.bodies[0])

    def test_deepseek_thinking_echoes_its_reasoning(self):
        self._call(DEEPSEEK)
        self.assertEqual(self.bodies[0]["thinking"], {"type": "enabled"})
        self.assertEqual(self.bodies[0]["messages"][1]["reasoning_content"], "pondering")

    def test_a_refusal_is_retried_once_without_the_parameter_and_remembered(self):
        self.replies = [ApiResponseError(400, OPENAI_REFUSAL)]
        self.assertEqual(self._call(OPENAI).text, "done")
        self.assertEqual(len(self.bodies), 2)
        self.assertIn("reasoning_effort", self.bodies[0])
        self.assertNotIn("reasoning_effort", self.bodies[1])
        self.assertEqual(self.remembered, [False])

    def test_a_remembered_refusal_is_never_sent_again(self):
        self.supports_thinking = False
        self._call(OPENAI)
        self.assertEqual(len(self.bodies), 1)
        self.assertNotIn("reasoning_effort", self.bodies[0])

    def test_a_refused_deepseek_switch_falls_back_to_disabled_without_echo(self):
        self.replies = [ApiResponseError(400, "Unknown field: thinking")]
        self._call(DEEPSEEK)
        self.assertEqual(self.bodies[1]["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_content", json.dumps(self.bodies[1]["messages"]))

    def test_a_streamed_refusal_is_not_taken_for_a_streaming_one(self):
        self.replies = [ApiResponseError(400, "reasoning_effort is not supported when stream is set")]
        self.assertEqual(self._call(OPENAI, on_chunk=lambda text: None).text, "done")
        self.assertEqual(self.remembered, [False])
        self.assertNotIn("reasoning_effort", self.bodies[1])

    def test_other_errors_are_raised_and_change_nothing(self):
        self.replies = [ApiResponseError(400, "maximum context length exceeded")]
        with self.assertRaises(ApiResponseError):
            self._call(OPENAI)
        self.assertEqual(self.remembered, [])

    def test_without_the_switch_a_reasoning_complaint_is_not_ours_to_swallow(self):
        self.replies = [ApiResponseError(400, OPENAI_REFUSAL)]
        with mock.patch.object(transport, "get_reasoning_enabled", lambda: False), self.assertRaises(ApiResponseError):
            self._call(OPENAI)
        self.assertEqual(self.remembered, [])


if __name__ == "__main__":
    unittest.main()
