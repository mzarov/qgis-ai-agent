import json
import unittest

from qgis_ai_agent.core.llm import anthropic, transport
from qgis_ai_agent.core.llm.anthropic_stream import AnthropicExchange, StreamedMessage, consume_anthropic
from qgis_ai_agent.core.llm.client import ApiResponseError
from qgis_ai_agent.core.llm.stream import SseAccumulator

URL = "https://api.anthropic.com"


def event(payload: dict) -> bytes:
    return f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n".encode()


def block_start(index: int, block: dict) -> bytes:
    return event({"type": "content_block_start", "index": index, "content_block": block})


def block_delta(index: int, delta: dict) -> bytes:
    return event({"type": "content_block_delta", "index": index, "delta": delta})


def block_stop(index: int) -> bytes:
    return event({"type": "content_block_stop", "index": index})


TEXT_STREAM = [
    event({"type": "message_start", "message": {"usage": {"input_tokens": 12, "output_tokens": 1}}}),
    block_start(0, {"type": "text", "text": ""}),
    block_delta(0, {"type": "text_delta", "text": "Hel"}),
    block_delta(0, {"type": "text_delta", "text": "lo"}),
    block_stop(0),
    event({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}}),
    event({"type": "message_stop"}),
]


class FoldingTest(unittest.TestCase):
    def test_text_deltas_join_into_one_block(self):
        data = consume_anthropic(TEXT_STREAM)
        self.assertEqual(data["content"], [{"type": "text", "text": "Hello"}])

    def test_the_folded_stream_parses_like_an_ordinary_response(self):
        text, calls, stop = anthropic.parse_response(consume_anthropic(TEXT_STREAM))
        self.assertEqual(text, "Hello")
        self.assertEqual(calls, [])
        self.assertEqual(stop, "end_turn")

    def test_deltas_reach_the_callback_as_they_arrive(self):
        seen: list[str] = []
        consume_anthropic(TEXT_STREAM, seen.append)
        self.assertEqual(seen, ["Hel", "lo"])

    def test_usage_survives_both_halves_of_the_stream(self):
        self.assertEqual(transport.parse_usage(consume_anthropic(TEXT_STREAM)), (12, 9))

    def test_an_event_split_across_chunks_is_reassembled(self):
        whole = b"".join(TEXT_STREAM)
        halves = [whole[: len(whole) // 2], whole[len(whole) // 2 :]]
        self.assertEqual(consume_anthropic(halves)["content"], [{"type": "text", "text": "Hello"}])

    def test_thinking_deltas_build_a_block_with_its_signature(self):
        chunks = [
            block_start(0, {"type": "thinking", "thinking": "", "signature": ""}),
            block_delta(0, {"type": "thinking_delta", "thinking": "pond"}),
            block_delta(0, {"type": "thinking_delta", "thinking": "ering"}),
            block_delta(0, {"type": "signature_delta", "signature": "sig-1"}),
            block_stop(0),
        ]
        text, blocks = anthropic.parse_thinking(consume_anthropic(chunks))
        self.assertEqual(text, "pondering")
        self.assertEqual(blocks[0]["signature"], "sig-1")

    def test_thinking_reaches_its_own_callback(self):
        seen: list[str] = []
        consume_anthropic(
            [
                block_start(0, {"type": "thinking", "thinking": ""}),
                block_delta(0, {"type": "thinking_delta", "thinking": "hmm"}),
            ],
            None,
            seen.append,
        )
        self.assertEqual(seen, ["hmm"])

    def test_tool_arguments_accumulate_out_of_partial_json(self):
        chunks = [
            block_start(0, {"type": "tool_use", "id": "toolu_1", "name": "list_layers"}),
            block_delta(0, {"type": "input_json_delta", "partial_json": '{"only'}),
            block_delta(0, {"type": "input_json_delta", "partial_json": '_visible": true}'}),
            block_stop(0),
        ]
        _, calls, _ = anthropic.parse_response(consume_anthropic(chunks))
        self.assertEqual(calls[0]["name"], "list_layers")
        self.assertEqual(calls[0]["input"], {"only_visible": True})

    def test_broken_tool_arguments_do_not_crash_the_fold(self):
        chunks = [
            block_start(0, {"type": "tool_use", "id": "t", "name": "x"}),
            block_delta(0, {"type": "input_json_delta", "partial_json": "{ not json"}),
            block_stop(0),
        ]
        _, calls, _ = anthropic.parse_response(consume_anthropic(chunks))
        self.assertEqual(calls[0]["input"], {})

    def test_blocks_keep_their_index_order(self):
        chunks = [
            block_start(1, {"type": "text", "text": "second"}),
            block_start(0, {"type": "thinking", "thinking": "first"}),
        ]
        self.assertEqual([block["type"] for block in consume_anthropic(chunks)["content"]], ["thinking", "text"])

    def test_text_stops_reaching_the_ui_once_a_tool_call_starts(self):
        seen: list[str] = []
        consume_anthropic(
            [
                block_start(0, {"type": "tool_use", "id": "t", "name": "x"}),
                block_delta(0, {"type": "input_json_delta", "partial_json": "{}"}),
                block_start(1, {"type": "text", "text": ""}),
                block_delta(1, {"type": "text_delta", "text": "chatter"}),
            ],
            seen.append,
        )
        self.assertEqual(seen, [])

    def test_a_ping_changes_nothing(self):
        self.assertEqual(consume_anthropic([event({"type": "ping"})])["content"], [])

    def test_a_delta_without_its_block_is_ignored(self):
        self.assertEqual(consume_anthropic([block_delta(3, {"type": "text_delta", "text": "x"})])["content"], [])

    def test_malformed_json_is_skipped(self):
        self.assertEqual(consume_anthropic([b"data: { not json\n\n"])["content"], [])


class ExchangeTest(unittest.TestCase):
    def setUp(self):
        import qgis_ai_agent.core.llm.anthropic_stream as module

        self.module = module
        self.saved = (
            module.post_stream,
            module.post_json,
            module.get_supports_streaming,
            module.set_supports_streaming,
        )
        self.flags: list[bool] = []
        self.supported = None
        module.get_supports_streaming = lambda url: self.supported
        module.set_supports_streaming = lambda url, value: self.flags.append(value)
        module.post_json = lambda *a, **k: {"content": [{"type": "text", "text": "plain"}]}

    def tearDown(self):
        (
            self.module.post_stream,
            self.module.post_json,
            self.module.get_supports_streaming,
            self.module.set_supports_streaming,
        ) = self.saved

    def _exchange(self, on_chunk=None):
        return AnthropicExchange("https://api.anthropic.com/v1/messages", {}, 10, URL, {}, on_chunk, None)

    def _streaming(self, *chunks):
        def fake(endpoint, headers, body, message, timeout, verify=None):
            accumulator = SseAccumulator()
            for chunk in chunks:
                for stream_event in accumulator.feed(chunk):
                    message.take(stream_event)
            return message.response()

        return fake

    def test_without_a_callback_nothing_is_streamed(self):
        self.module.post_stream = lambda *a: self.fail("streaming must not be attempted")
        self.assertEqual(self._exchange().send({})["content"][0]["text"], "plain")

    def test_a_known_bad_endpoint_is_not_streamed_again(self):
        self.supported = False
        self.module.post_stream = lambda *a: self.fail("streaming must not be attempted")
        self.assertEqual(self._exchange(lambda t: None).send({})["content"][0]["text"], "plain")

    def test_a_working_stream_is_used_and_remembered(self):
        self.module.post_stream = self._streaming(*TEXT_STREAM)
        data = self._exchange(lambda t: None).send({})
        self.assertEqual(data["content"], [{"type": "text", "text": "Hello"}])
        self.assertEqual(self.flags, [True])

    def test_the_stream_flag_is_added_to_the_body(self):
        seen = {}

        def fake(endpoint, headers, body, message, timeout, verify=None):
            seen.update(body)
            return self._streaming(*TEXT_STREAM)(endpoint, headers, body, message, timeout, verify)

        self.module.post_stream = fake
        self._exchange(lambda t: None).send({"model": "claude"})
        self.assertTrue(seen["stream"])
        self.assertEqual(seen["model"], "claude")

    def test_a_refused_stream_falls_back_and_is_remembered(self):
        def fake(*a, **k):
            raise ApiResponseError(400, "streaming is not supported")

        self.module.post_stream = fake
        self.assertEqual(self._exchange(lambda t: None).send({})["content"][0]["text"], "plain")
        self.assertEqual(self.flags, [False])

    def test_a_bad_key_does_not_disable_streaming(self):
        def fake(*a, **k):
            raise ApiResponseError(401, "invalid x-api-key")

        self.module.post_stream = fake
        with self.assertRaises(ApiResponseError):
            self._exchange(lambda t: None).send({})
        self.assertEqual(self.flags, [])

    def test_a_thinking_refusal_is_raised_for_the_caller_to_retry(self):
        def fake(*a, **k):
            raise ApiResponseError(400, "thinking is not supported by this model")

        self.module.post_stream = fake
        with self.assertRaises(ApiResponseError):
            self._exchange(lambda t: None).send({})
        self.assertEqual(self.flags, [])

    def test_an_empty_stream_counts_as_a_refusal(self):
        self.module.post_stream = self._streaming(event({"type": "ping"}))
        self.assertEqual(self._exchange(lambda t: None).send({})["content"][0]["text"], "plain")
        self.assertEqual(self.flags, [False])


class CallAnthropicTest(unittest.TestCase):
    def setUp(self):
        import qgis_ai_agent.core.llm.anthropic_stream as stream_module

        self.stream_module = stream_module
        self.saved_stream = (stream_module.post_stream, stream_module.get_supports_streaming)
        self.saved_transport = (transport.build_request, transport.get_supports_thinking, transport.get_thinking_budget)
        self.thinking_flags: list[bool] = []
        self.budget = 0
        stream_module.get_supports_streaming = lambda url: None
        stream_module.set_supports_streaming = lambda url, value: None
        transport.build_request = lambda *a: ("https://api.anthropic.com/v1/messages", {}, "claude")
        transport.get_supports_thinking = lambda url: None
        transport.get_thinking_budget = lambda: self.budget
        transport.set_supports_thinking = lambda url, value: self.thinking_flags.append(value)

    def tearDown(self):
        self.stream_module.post_stream, self.stream_module.get_supports_streaming = self.saved_stream
        transport.build_request, transport.get_supports_thinking, transport.get_thinking_budget = self.saved_transport

    def _serve(self, *chunks):
        def fake(endpoint, headers, body, message, timeout, verify=None):
            self.bodies.append(body)
            accumulator = SseAccumulator()
            for chunk in chunks:
                for stream_event in accumulator.feed(chunk):
                    message.take(stream_event)
            return message.response()

        self.bodies: list[dict] = []
        return fake

    def test_a_streamed_answer_becomes_a_model_turn(self):
        self.stream_module.post_stream = self._serve(*TEXT_STREAM)
        seen: list[str] = []
        turn = transport._call_anthropic([], [], {}, 10, URL, seen.append)
        self.assertEqual(turn.text, "Hello")
        self.assertEqual(seen, ["Hel", "lo"])
        self.assertEqual((turn.input_tokens, turn.output_tokens), (12, 9))

    def test_a_thinking_refusal_retries_the_stream_without_it(self):
        self.budget = 2048
        served = self._serve(*TEXT_STREAM)
        attempts: list[dict] = []

        def fake(endpoint, headers, body, message, timeout, verify=None):
            attempts.append(body)
            if len(attempts) == 1:
                raise ApiResponseError(400, "thinking is not supported by this model")
            return served(endpoint, headers, body, message, timeout, verify)

        self.stream_module.post_stream = fake
        turn = transport._call_anthropic([], [], {}, 10, URL, lambda text: None)
        self.assertEqual(turn.text, "Hello")
        self.assertIn("thinking", attempts[0])
        self.assertNotIn("thinking", attempts[1])
        self.assertEqual(self.thinking_flags, [False])


class StreamedMessageDirectTest(unittest.TestCase):
    def test_an_untouched_fold_is_empty(self):
        self.assertEqual(StreamedMessage().response(), {"content": [], "stop_reason": "", "usage": {}})


if __name__ == "__main__":
    unittest.main()
