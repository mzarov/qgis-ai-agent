import json
import unittest

from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent import notices
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.llm import anthropic, retry, transport, turns
from ai_agent.core.llm.anthropic_stream import StreamedMessage
from ai_agent.core.llm.client import ApiResponseError, blocking_timeout, scrub_secrets
from ai_agent.core.llm.parser import parse_model_json
from ai_agent.core.llm.refusals import may_reject_images, streaming_unsupported, thinking_unsupported, tools_unsupported
from ai_agent.core.llm.stream import SseAccumulator, StreamedCompletion
from ai_agent.core.llm.stream_runner import STREAM_EVENTS_KEY, _finished_response
from ai_agent.core.llm.thinking import split_thinking
from ai_agent.core.llm.turns import ModelTurn, ToolCall

OVERFLOW = json.dumps(
    {
        "error": {
            "message": "This model's maximum context length is 128000 tokens. However, your messages and functions "
            "resulted in 130000 tokens.",
            "code": "context_length_exceeded",
        }
    }
)


def fold(stream_class, *chunks):
    accumulator = SseAccumulator()
    completion = stream_class()
    for chunk in chunks:
        for event in accumulator.feed(chunk):
            completion.take(event)
    for event in accumulator.flush():
        completion.take(event)
    return completion, accumulator


class RefusalTest(unittest.TestCase):
    def test_a_context_overflow_is_never_a_refusal(self):
        error = ApiResponseError(400, OVERFLOW)
        self.assertFalse(tools_unsupported(error))
        self.assertFalse(streaming_unsupported(error))
        self.assertFalse(may_reject_images(error, (400,)))

    def test_words_inside_other_words_do_not_count(self):
        error = ApiResponseError(400, "upstream processed the request but the payload was malformed")
        self.assertFalse(streaming_unsupported(error))
        self.assertFalse(tools_unsupported(error))

    def test_a_genuine_refusal_is_recognised(self):
        self.assertTrue(tools_unsupported(ApiResponseError(400, "This model does not support tools.")))
        self.assertTrue(streaming_unsupported(ApiResponseError(400, "stream is not supported by this endpoint")))
        self.assertTrue(thinking_unsupported(ApiResponseError(400, "Unknown field: thinking")))

    def test_a_structured_parameter_is_enough(self):
        body = json.dumps({"error": {"message": "Unrecognized request argument", "param": "tools"}})
        self.assertTrue(tools_unsupported(ApiResponseError(400, body)))

    def test_a_signature_binding_error_is_not_a_thinking_refusal(self):
        body = "Invalid `signature` in `thinking` block. The block is bound to a different conversation."
        self.assertFalse(thinking_unsupported(ApiResponseError(400, body)))


class SseTest(unittest.TestCase):
    def test_a_cyrillic_letter_split_between_reads_survives(self):
        raw = 'data: {"choices": [{"delta": {"content": "Привет"}}]}\n\n'.encode()
        cut = raw.index("П".encode()) + 1
        completion, _ = fold(StreamedCompletion, raw[:cut], raw[cut:])
        self.assertEqual(completion.response()["choices"][0]["message"]["content"], "Привет")

    def test_multi_line_data_joins_into_one_event(self):
        accumulator = SseAccumulator()
        self.assertEqual(accumulator.feed(b'data: {"a":\ndata: 1}\n\n'), ['{"a":\n1}'])

    def test_a_last_line_without_newline_is_flushed(self):
        accumulator = SseAccumulator()
        self.assertEqual(accumulator.feed(b'data: {"a": 1}'), [])
        self.assertEqual(accumulator.flush(), ['{"a": 1}'])

    def test_a_plain_json_body_is_kept_for_servers_that_ignore_stream(self):
        accumulator = SseAccumulator()
        accumulator.feed(b'{"choices": []}')
        accumulator.flush()
        self.assertEqual(accumulator.plain_json(), {"choices": []})


class StreamEndingTest(unittest.TestCase):
    def test_an_error_event_inside_an_anthropic_stream_is_raised(self):
        completion, accumulator = fold(
            StreamedMessage,
            b'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}\n\n',
            b'data: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}\n\n',
        )
        with self.assertRaises(ApiResponseError) as caught:
            _finished_response(completion, accumulator, "https://api.anthropic.com/v1/messages")
        self.assertEqual(caught.exception.status_code, 529)

    def test_an_error_event_inside_an_openai_stream_is_raised(self):
        completion, accumulator = fold(StreamedCompletion, b'data: {"error": {"message": "upstream failed"}}\n\n')
        with self.assertRaises(ApiResponseError):
            _finished_response(completion, accumulator, "https://example.com/v1")

    def test_a_stream_without_its_terminator_is_incomplete(self):
        completion, accumulator = fold(StreamedCompletion, b'data: {"choices": [{"delta": {"content": "Hel"}}]}\n\n')
        with self.assertRaises(ConnectionError):
            _finished_response(completion, accumulator, "https://example.com/v1")

    def test_a_complete_stream_reports_its_event_count(self):
        completion, accumulator = fold(
            StreamedCompletion,
            b'data: {"choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}\n\n',
            b"data: [DONE]\n\n",
        )
        response = _finished_response(completion, accumulator, "https://example.com/v1")
        self.assertEqual(response[STREAM_EVENTS_KEY], 2)

    def test_whole_tool_calls_without_index_stay_separate(self):
        first = {"id": "a", "function": {"name": "list_layers", "arguments": "{}"}}
        second = {"id": "b", "function": {"name": "describe_layer", "arguments": '{"layer_name": "x"}'}}
        chunks = [
            f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [call]}}]})}\n\n".encode()
            for call in (first, second)
        ]
        completion, _ = fold(StreamedCompletion, *chunks)
        calls = completion.response()["choices"][0]["message"]["tool_calls"]
        self.assertEqual([call["function"]["name"] for call in calls], ["list_layers", "describe_layer"])


class ParsingTest(unittest.TestCase):
    def test_anthropic_cache_tokens_count_as_input(self):
        usage = {"input_tokens": 12, "cache_read_input_tokens": 40000, "cache_creation_input_tokens": 3000}
        self.assertEqual(transport.parse_usage({"usage": {**usage, "output_tokens": 200}}), (43012, 200))

    def test_openai_prompt_tokens_are_taken_as_is(self):
        self.assertEqual(transport.parse_usage({"usage": {"prompt_tokens": 50, "completion_tokens": 5}}), (50, 5))

    def test_a_scalar_json_reply_is_an_answer_not_a_crash(self):
        turn = turns.parse_json_turn({"choices": [{"message": {"content": "3"}}]})
        self.assertEqual(turn.text, "3")

    def test_prose_quoting_json_keeps_the_prose(self):
        content = 'Here is GeoJSON: {"type": "Point", "coordinates": [1, 2]} for you.'
        turn = turns.parse_json_turn({"choices": [{"message": {"content": content}}]})
        self.assertEqual(turn.text, content)

    def test_a_single_call_object_is_accepted(self):
        content = json.dumps({"text": "", "tool_calls": {"name": "list_layers", "arguments": {}}})
        turn = turns.parse_json_turn({"choices": [{"message": {"content": content}}]})
        self.assertEqual([call.name for call in turn.tool_calls], ["list_layers"])

    def test_parse_model_json_never_returns_a_scalar(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_model_json("3")

    def test_an_unopened_closing_think_tag_ends_the_reasoning(self):
        self.assertEqual(split_thinking("reasoning here</think>Answer"), ("Answer", "reasoning here"))
        self.assertEqual(split_thinking("<think>a</think>b"), ("b", "a"))


class RetryPolicyTest(unittest.TestCase):
    def test_every_server_error_is_retried(self):
        self.assertTrue(retry.is_retryable(ApiResponseError(529, "overloaded"), 0))
        self.assertTrue(retry.is_retryable(ApiResponseError(520, "x"), 0))
        self.assertFalse(retry.is_retryable(ApiResponseError(400, "x"), 0))

    def test_an_exhausted_quota_is_not_retried(self):
        self.assertFalse(retry.is_retryable(ApiResponseError(429, '{"error": {"code": "insufficient_quota"}}'), 0))

    def test_retry_after_is_honoured_and_capped(self):
        self.assertEqual(retry.retry_delay(ApiResponseError(429, "", retry_after=7), 1), 7)
        self.assertEqual(
            retry.retry_delay(ApiResponseError(429, "", retry_after=600), 1), retry.MAX_RETRY_AFTER_SECONDS
        )
        self.assertEqual(retry.retry_delay(ApiResponseError(429, ""), 1), retry.BACKOFF_SECONDS[0])

    def test_reasoning_counts_as_delivered(self):
        seen = []
        guard = retry.ChunkGuard(None)
        guard.wrap(seen.append)("thought")
        self.assertEqual((guard.delivered, seen), (1, ["thought"]))
        self.assertIsNone(guard.wrap(None))

    def test_blocking_calls_wait_longer_than_the_stream_idle_limit(self):
        self.assertGreater(blocking_timeout(120), 120)


class ThinkingConfigTest(unittest.TestCase):
    def test_models_that_always_think_never_get_disabled_or_a_budget(self):
        for model in ("claude-fable-5-1", "claude-opus-5-5", "claude-mythos-5-1"):
            for budget in (0, 4096):
                with self.subTest(model=model, budget=budget):
                    self.assertEqual(
                        anthropic.thinking_config(model, budget), {"type": "adaptive", "display": "summarized"}
                    )

    def test_the_adaptive_generation_never_gets_budget_tokens(self):
        self.assertEqual(anthropic.thinking_config("claude-opus-5", 4096)["type"], "adaptive")
        self.assertEqual(anthropic.thinking_config("claude-opus-5", 0), {})
        self.assertEqual(anthropic.thinking_config("claude-sonnet-5", 0), {"type": "disabled"})
        self.assertEqual(anthropic.thinking_config("claude-opus-4-6", 2048), {"type": "adaptive"})

    def test_older_models_keep_the_budget(self):
        self.assertEqual(
            anthropic.thinking_config("claude-haiku-4-5", 2048), {"type": "enabled", "budget_tokens": 2048}
        )
        self.assertEqual(anthropic.thinking_config("claude-haiku-4-5", 0), {})

    def test_thinking_blocks_go_back_to_models_that_think_by_default(self):
        messages = [
            {
                "role": "assistant",
                "content": "a",
                "thinking_blocks": [{"type": "thinking", "thinking": "", "signature": "s"}],
            }
        ]
        body = anthropic.build_body(messages, [], "claude-opus-5", thinking_budget=0)
        self.assertEqual(body["messages"][0]["content"][0]["type"], "thinking")

    def test_binding_is_requested_only_when_asked_and_only_for_binding_models(self):
        bound = anthropic.build_body([{"role": "user", "content": "x"}], [], "claude-fable-5-1", bind_thinking=True)
        self.assertEqual(bound["thinking"]["block_binding"], {"prefix_mismatch_behavior": "drop_block"})
        loose = anthropic.build_body([{"role": "user", "content": "x"}], [], "claude-opus-5", bind_thinking=True)
        self.assertNotIn("block_binding", loose.get("thinking", {}))

    def test_adaptive_thinking_gets_room_to_answer(self):
        body = anthropic.build_body([{"role": "user", "content": "x"}], [], "claude-opus-5-5")
        self.assertGreaterEqual(body["max_tokens"], anthropic.ADAPTIVE_MAX_TOKENS)

    def test_the_beta_header_is_merged_not_replaced(self):
        merged = transport._with_beta({"anthropic-beta": "a"}, anthropic.BINDING_BETA)
        self.assertEqual(merged["anthropic-beta"], f"a,{anthropic.BINDING_BETA}")


class _Request:
    messages: list = []
    tool_schemas: list = []
    overrides: dict = {}
    protocol = "native"


class CutOffCallsTest(unittest.TestCase):
    def test_calls_cut_off_by_the_output_limit_do_not_run(self):
        saved = loop_module.build_step_request
        loop_module.build_step_request = lambda *args, **kwargs: _Request()
        loop = AgentLoop()
        loop._turn.start = lambda *args: None
        ran = []
        loop._dispatch = lambda call: ran.append(call)
        try:
            loop.start("task", [])
            loop._on_turn(
                ModelTurn(tool_calls=[ToolCall(id="c", name="run_python", arguments={})], finish_reason="max_tokens")
            )
        finally:
            loop_module.build_step_request = saved
            loop.abort()
        self.assertEqual(ran, [])
        results = loop._transcript.entries[-1]["results"]
        self.assertEqual(results[0].payload["error"], notices.CALLS_CUT_OFF)


class SecretScrubTest(unittest.TestCase):
    def test_keys_in_error_bodies_are_masked(self):
        text = "bad key sk-ant-qwertyuiopasdfgh, Authorization: Bearer zxcvbnmlkjhg"  # pragma: allowlist secret
        self.assertNotIn("qwertyuiop", scrub_secrets(text))
        self.assertNotIn("zxcvbnmlkjhg", scrub_secrets(text))
        self.assertNotIn("qwertyuiop", str(ApiResponseError(401, text)))


if __name__ == "__main__":
    unittest.main()
