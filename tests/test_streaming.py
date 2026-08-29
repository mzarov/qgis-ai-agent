import json
import pathlib
import unittest

from qgis_ai_agent.core.llm import transport
from qgis_ai_agent.core.llm.client import ApiResponseError
from qgis_ai_agent.core.llm.stream import SseAccumulator, consume

SCHEMAS = [{"type": "function", "function": {"name": "list_layers", "parameters": {}}}]
URL = "https://api.example/v1"


def streaming(*chunks):
    def fake(endpoint, headers, body, completion, timeout, verify=None):
        accumulator = SseAccumulator()
        for chunk in chunks:
            for stream_event in accumulator.feed(chunk):
                completion.take(stream_event)
        return completion.response()

    return fake


def event(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def text_delta(text: str) -> bytes:
    return event({"choices": [{"delta": {"content": text}}]})


class SseAccumulatorTest(unittest.TestCase):
    def setUp(self):
        self.accumulator = SseAccumulator()

    def test_a_whole_event_is_returned(self):
        self.assertEqual(self.accumulator.feed(b'data: {"a": 1}\n\n'), ['{"a": 1}'])

    def test_an_event_split_across_chunks_is_reassembled(self):
        self.assertEqual(self.accumulator.feed(b'data: {"a": '), [])
        self.assertEqual(self.accumulator.feed(b"1}\n\n"), ['{"a": 1}'])

    def test_a_partial_trailing_event_is_held_back(self):
        self.assertEqual(self.accumulator.feed(b'data: {"a": 1}\n\ndata: {"b"'), ['{"a": 1}'])

    def test_several_events_in_one_chunk_keep_order(self):
        self.assertEqual(
            self.accumulator.feed(b"data: one\n\ndata: two\n\n"),
            ["one", "two"],
        )

    def test_carriage_returns_are_normalised(self):
        self.assertEqual(self.accumulator.feed(b"data: one\r\n\r\n"), ["one"])

    def test_non_data_lines_are_ignored(self):
        self.assertEqual(self.accumulator.feed(b": ping\nevent: x\ndata: one\n\n"), ["one"])


class StreamedCompletionTest(unittest.TestCase):
    def test_text_deltas_are_joined_and_forwarded(self):
        seen = []
        data = consume([text_delta("Hel"), text_delta("lo")], seen.append)
        self.assertEqual(data["choices"][0]["message"]["content"], "Hello")
        self.assertEqual(seen, ["Hel", "lo"])

    def test_the_done_marker_is_not_parsed_as_json(self):
        data = consume([text_delta("hi"), b"data: [DONE]\n\n"])
        self.assertEqual(data["choices"][0]["message"]["content"], "hi")

    def test_malformed_json_is_skipped_instead_of_crashing(self):
        data = consume([b"data: {not json\n\n", text_delta("ok")])
        self.assertEqual(data["choices"][0]["message"]["content"], "ok")

    def test_tool_call_deltas_accumulate_across_chunks(self):
        chunks = [
            event(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "id": "c1", "function": {"name": "list_", "arguments": '{"a"'}}
                                ]
                            }
                        }
                    ]
                }
            ),
            event({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": 1}"}}]}}]}),
        ]
        calls = consume(chunks)["choices"][0]["message"]["tool_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["id"], "c1")
        self.assertEqual(calls[0]["function"]["name"], "list_")
        self.assertEqual(calls[0]["function"]["arguments"], '{"a": 1}')

    def test_parallel_tool_calls_keep_their_index_order(self):
        chunks = [
            event({"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "b", "function": {"name": "second"}}]}}]}),
            event({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a", "function": {"name": "first"}}]}}]}),
        ]
        calls = consume(chunks)["choices"][0]["message"]["tool_calls"]
        self.assertEqual([call["function"]["name"] for call in calls], ["first", "second"])

    def test_usage_is_carried_out_of_the_stream(self):
        data = consume(
            [text_delta("hi"), event({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}})]
        )
        self.assertEqual(transport.parse_usage(data), (7, 3))

    def test_a_stream_without_usage_reports_nothing_spent(self):
        self.assertEqual(transport.parse_usage(consume([text_delta("hi")])), (0, 0))

    def test_the_finish_reason_survives(self):
        data = consume([event({"choices": [{"delta": {}, "finish_reason": "stop"}]})])
        self.assertEqual(data["choices"][0]["finish_reason"], "stop")

    def test_a_streamed_answer_parses_into_a_model_turn(self):
        turn = transport._parse_native_turn(consume([text_delta("done")]))
        self.assertEqual(turn.text, "done")
        self.assertEqual(turn.tool_calls, [])


class StreamingDispatchTest(unittest.TestCase):
    def setUp(self):
        self.flags = []
        self.saved = {
            "post_stream": transport.post_stream,
            "get": transport.get_supports_streaming,
            "set": transport.set_supports_streaming,
            "tools": transport.set_supports_tools,
            "supports_tools": transport.get_supports_tools,
            "chat": transport.post_chat_completion,
            "build": transport.build_request,
        }
        self.supported = None
        transport.get_supports_streaming = lambda url: self.supported
        transport.set_supports_streaming = lambda url, value: self.flags.append(value)
        transport.set_supports_tools = lambda url, value: None
        transport.get_supports_tools = lambda url: None
        transport.build_request = lambda *args: ("https://api.example/v1/chat/completions", {}, "model-x")
        transport.post_chat_completion = lambda *args, **kwargs: {"choices": [{"message": {"content": "not streamed"}}]}

    def tearDown(self):
        transport.post_stream = self.saved["post_stream"]
        transport.get_supports_streaming = self.saved["get"]
        transport.set_supports_streaming = self.saved["set"]
        transport.set_supports_tools = self.saved["tools"]
        transport.get_supports_tools = self.saved["supports_tools"]
        transport.post_chat_completion = self.saved["chat"]
        transport.build_request = self.saved["build"]

    def _call(self, on_chunk=None):
        return transport._dispatch([{"role": "user", "content": "hi"}], SCHEMAS, {}, 10, URL, on_chunk)

    def test_without_a_callback_the_stream_is_not_attempted(self):
        transport.post_stream = lambda *args: self.fail("streaming must not be attempted")
        self.assertEqual(self._call().text, "not streamed")

    def test_a_known_bad_endpoint_is_not_streamed_again(self):
        self.supported = False
        transport.post_stream = lambda *args: self.fail("streaming must not be attempted")
        self.assertEqual(self._call(lambda text: None).text, "not streamed")

    def test_a_working_stream_is_remembered(self):
        transport.post_stream = streaming(text_delta("streamed"))
        self.assertEqual(self._call(lambda text: None).text, "streamed")
        self.assertEqual(self.flags, [True])

    def test_the_request_body_asks_for_a_stream_with_usage(self):
        seen = {}

        def fake(endpoint, headers, body, completion, timeout, verify=None):
            seen.update(body)
            return streaming(text_delta("ok"))(endpoint, headers, body, completion, timeout, verify)

        transport.post_stream = fake
        self._call(lambda text: None)
        self.assertTrue(seen["stream"])
        self.assertTrue(seen["stream_options"]["include_usage"])
        self.assertEqual(seen["tools"], SCHEMAS)

    def test_a_refusing_endpoint_falls_back_and_is_remembered_as_broken(self):
        def fake(*args):
            raise ApiResponseError(400, "stream is not supported")

        transport.post_stream = fake
        self.assertEqual(self._call(lambda text: None).text, "not streamed")
        self.assertEqual(self.flags, [False])

    def test_a_bad_key_does_not_disable_streaming_for_ever(self):
        def fake(*args):
            raise ApiResponseError(401, "Incorrect API key provided")

        transport.post_stream = fake
        transport.post_chat_completion = fake
        with self.assertRaises(ApiResponseError):
            self._call(lambda text: None)
        self.assertEqual(self.flags, [])

    def test_a_rate_limit_does_not_disable_streaming_either(self):
        def fake(*args):
            raise ApiResponseError(429, "Rate limit reached")

        transport.post_stream = fake
        transport.post_chat_completion = fake
        with self.assertRaises(ApiResponseError):
            self._call(lambda text: None)
        self.assertEqual(self.flags, [])

    def test_a_server_that_ignores_the_stream_flag_falls_back(self):
        transport.post_stream = streaming(b'{"choices": [{"message": {"content": "plain"}}]}')
        self.assertEqual(self._call(lambda text: None).text, "not streamed")
        self.assertEqual(self.flags, [False])

    def test_deltas_reach_the_callback(self):
        seen = []

        transport.post_stream = streaming(text_delta("a"), text_delta("b"))
        self._call(seen.append)
        self.assertEqual(seen, ["a", "b"])

    def test_the_ssl_setting_reaches_the_stream(self):
        seen = []

        def fake(endpoint, headers, body, completion, timeout, verify=None):
            seen.append(verify)
            return streaming(text_delta("ok"))(endpoint, headers, body, completion, timeout, verify)

        transport.post_stream = fake
        transport._dispatch([], SCHEMAS, {"verify_override": False}, 10, URL, lambda text: None)
        self.assertEqual(seen, [False])


class StreamRunnerSourceTest(unittest.TestCase):
    SOURCE = (pathlib.Path(__file__).parent.parent / "qgis_ai_agent/core/llm/stream_runner.py").read_text()

    def test_the_request_is_built_the_same_way_as_every_other_one(self):
        self.assertIn("build_network_request", self.SOURCE)

    def test_no_third_party_http_library_sneaks_in(self):
        self.assertNotIn("import requests", self.SOURCE)
        self.assertNotIn("urllib", self.SOURCE)

    def test_an_instantly_finished_reply_does_not_enter_the_loop(self):
        self.assertIn("if not reply.isFinished():", self.SOURCE)

    def test_the_watchdog_restarts_on_every_incoming_chunk(self):
        self.assertIn("reply.readyRead.connect(watchdog.start)", self.SOURCE)


if __name__ == "__main__":
    unittest.main()
