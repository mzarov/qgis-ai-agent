import json
import pathlib
import unittest
from unittest import mock

from ai_agent.core.llm import transport, turns, worker
from ai_agent.core.llm.client import ApiResponseError
from ai_agent.core.llm.stream import SseAccumulator, StreamedCompletion
from ai_agent.core.llm.stream_runner import _finished_response as finished_response
from ai_agent.core.llm.transport import _openai_options
from ai_agent.core.llm.turns import ModelTurn

SCHEMAS = [{"type": "function", "function": {"name": "list_layers", "parameters": {}}}]
URL = "https://api.example/v1"


def consume(chunks, on_text=None, on_thinking=None):
    accumulator = SseAccumulator()
    completion = StreamedCompletion(on_text, on_thinking)
    for chunk in chunks:
        for event in accumulator.feed(chunk):
            completion.take(event)
    for event in accumulator.flush():
        completion.take(event)
    return completion.response()


DONE = b"data: [DONE]\n\n"


def streaming(*chunks, complete=True):
    def fake(endpoint, headers, body, completion, timeout, verify=None):
        accumulator = SseAccumulator()
        for chunk in (*chunks, DONE) if complete else chunks:
            for stream_event in accumulator.feed(chunk):
                completion.take(stream_event)
        for stream_event in accumulator.flush():
            completion.take(stream_event)
        return finished_response(completion, accumulator, endpoint)

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

    def test_whole_calls_that_share_index_zero_stay_apart(self):
        def whole(call_id, arguments):
            call = {"index": 0, "id": call_id, "type": "function", "function": {"name": "describe_layer"}}
            call["function"]["arguments"] = arguments
            return event({"choices": [{"delta": {"tool_calls": [call]}}]})

        chunks = [whole("call_a", '{"layer_name": "roads"}'), whole("call_b", '{"layer_name": "rivers"}')]
        calls = consume(chunks)["choices"][0]["message"]["tool_calls"]
        self.assertEqual(
            [(call["id"], call["function"]["arguments"]) for call in calls],
            [("call_a", '{"layer_name": "roads"}'), ("call_b", '{"layer_name": "rivers"}')],
        )

    def test_a_later_delta_without_an_id_follows_its_call_to_the_new_slot(self):
        def piece(arguments, call_id=None, name=None):
            call = {"index": 0, "function": {"arguments": arguments}}
            if call_id:
                call["id"], call["function"]["name"] = call_id, name
            return event({"choices": [{"delta": {"tool_calls": [call]}}]})

        chunks = [piece('{"a": 1}', "first", "one"), piece('{"b": ', "second", "two"), piece("2}")]
        calls = consume(chunks)["choices"][0]["message"]["tool_calls"]
        self.assertEqual(
            [(call["function"]["name"], call["function"]["arguments"]) for call in calls],
            [("one", '{"a": 1}'), ("two", '{"b": 2}')],
        )

    def test_arguments_streamed_as_an_object_stay_json(self):
        call = {"index": 0, "id": "c1", "function": {"name": "list_layers", "arguments": {"limit": 5}}}
        turn = turns.parse_native_turn(consume([event({"choices": [{"delta": {"tool_calls": [call]}}]})]))
        self.assertEqual(turn.tool_calls[0].arguments, {"limit": 5})

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
        turn = turns.parse_native_turn(consume([text_delta("done")]))
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
        transport.get_supports_streaming = lambda url, model=None, dialect=None: self.supported
        transport.set_supports_streaming = lambda url, value, model=None, dialect=None: self.flags.append(value)
        transport.set_supports_tools = lambda url, value, model=None, dialect=None: None
        transport.get_supports_tools = lambda url, model=None, dialect=None: None
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

    def test_a_thinking_only_turn_does_not_disable_streaming(self):
        reasoning = event({"choices": [{"delta": {"reasoning_content": "the whole turn is thought"}}]})
        transport.post_stream = streaming(reasoning)
        turn = self._call(lambda text: None)
        self.assertEqual(turn.thinking, "the whole turn is thought")
        self.assertEqual(self.flags, [True])

    def test_a_server_that_ignores_the_stream_flag_falls_back(self):
        transport.post_stream = streaming(b'{"choices": [{"message": {"content": "plain"}}]}', complete=False)
        self.assertEqual(self._call(lambda text: None).text, "plain")
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

    def test_capability_lookup_includes_endpoint_model_and_resolved_dialect(self):
        seen = []
        transport.get_supports_tools = lambda *scope: seen.append(scope) or False
        transport._dispatch(
            [],
            SCHEMAS,
            {"model_override": "model-b", "dialect_override": "openai"},
            10,
            URL,
        )
        self.assertEqual(seen, [(URL, "model-b", "openai")])


OLLAMA_TOOLS_REFUSAL = (
    '{"error":{"message":"registry.ollama.ai/library/gemma2:2b does not support tools",'
    '"type":"api_error","param":null,"code":null}}'
)


class ToolLessStreamingTest(unittest.TestCase):
    def setUp(self):
        self.streaming_flags, self.tools_flags, self.bodies, self.blocking = [], [], [], []
        self.supports_tools = None
        self.reply = '{"text": "answered without tools"}'
        for name, value in (
            ("post_stream", self.stream),
            ("post_chat_completion", self.post),
            ("build_request", lambda *args: ("http://localhost:11434/v1/chat/completions", {}, "gemma2:2b")),
            ("get_supports_streaming", lambda *args: None),
            ("set_supports_streaming", lambda url, value, *args: self.streaming_flags.append(value)),
            ("get_supports_tools", lambda *args: self.supports_tools),
            ("set_supports_tools", lambda url, value, *args: self.tools_flags.append(value)),
            ("get_reasoning_enabled", lambda: False),
        ):
            patch = mock.patch.object(transport, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def stream(self, endpoint, headers, body, completion, timeout, verify=None, **options):
        self.bodies.append(body)
        if body.get("tools"):
            raise ApiResponseError(400, OLLAMA_TOOLS_REFUSAL)
        return streaming(text_delta(self.reply))(endpoint, headers, body, completion, timeout, verify)

    def post(self, messages, extra_body=None, **options):
        self.blocking.append(extra_body or {})
        if (extra_body or {}).get("tools"):
            raise ApiResponseError(400, OLLAMA_TOOLS_REFUSAL)
        return {"choices": [{"message": {"content": self.reply}, "finish_reason": "stop"}]}

    def dispatch(self, schemas=SCHEMAS, on_chunk=None):
        return transport._dispatch(
            [{"role": "user", "content": "hi"}], schemas, {}, 10, "http://localhost:11434/v1", on_chunk
        )

    def test_a_model_without_tools_falls_back_to_the_json_protocol_on_a_streaming_endpoint(self):
        turn = self.dispatch(on_chunk=lambda text: None)
        self.assertEqual((turn.text, turn.protocol), ("answered without tools", turns.PROTOCOL_JSON))
        self.assertEqual(self.tools_flags, [False])
        self.assertNotIn(False, self.streaming_flags, "a refusal of tools says nothing about streaming")
        self.assertEqual([bool(body.get("tools")) for body in self.bodies], [True, False])
        self.assertEqual(self.blocking, [])

    def test_a_json_protocol_reply_streams_without_showing_its_json(self):
        self.supports_tools = False
        self.reply = '{"text": "Listing.", "tool_calls": [{"name": "list_layers", "arguments": {}}]}'
        shown = []
        turn = self.dispatch(on_chunk=shown.append)
        self.assertEqual([call.name for call in turn.tool_calls], ["list_layers"])
        self.assertEqual(shown, [])
        self.assertEqual(self.blocking, [])
        self.assertEqual(self.tools_flags, [])

    def test_a_tool_less_request_streams_and_never_claims_tool_support(self):
        self.reply = "A summary."
        shown = []
        turn = self.dispatch([], shown.append)
        self.assertEqual((turn.text, "".join(shown)), ("A summary.", "A summary."))
        self.assertEqual(self.tools_flags, [])
        self.assertEqual(self.streaming_flags, [True])

    def test_a_tool_less_reply_quoting_json_is_kept_whole(self):
        self.reply = (
            "The user styles the roads layer.\n"
            'The label settings they asked for:\n```json\n{"text": "NAME", "size": 10}\n```\n'
            "- next: export the map to PDF"
        )
        for on_chunk in (None, lambda text: None):
            with self.subTest(streamed=on_chunk is not None):
                turn = self.dispatch([], on_chunk)
                self.assertEqual((turn.text, turn.protocol), (self.reply, turns.PROTOCOL_NATIVE))


class ReasoningOpenedInPromptTest(unittest.TestCase):
    REPLY = (text_delta("Thinking it over."), text_delta("</think>"), text_delta("Two layers."))

    def setUp(self):
        for name, value in (
            ("post_stream", streaming(*self.REPLY)),
            ("build_request", lambda *args: ("http://localhost:11434/v1/chat/completions", {}, "r1")),
            ("get_supports_streaming", lambda *args: True),
            ("get_supports_tools", lambda *args: True),
            ("get_reasoning_enabled", lambda: False),
            ("_OPENED_IN_PROMPT", set()),
        ):
            patch = mock.patch.object(transport, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def shown(self, model):
        shown = []
        overrides = {"model_override": model, "dialect_override": "openai"}
        turn = transport._dispatch([], SCHEMAS, overrides, 10, "http://localhost:11434/v1", shown.append)
        self.assertEqual(turn.text, "Two layers.")
        return "".join(shown)

    def test_once_a_model_closed_unopened_reasoning_its_next_drafts_hold_until_the_close(self):
        self.shown("r1")
        self.assertEqual(self.shown("r1"), "Two layers.")

    def test_a_reply_without_the_close_tag_gives_the_live_draft_back(self):
        self.shown("r1")
        transport.post_stream = streaming(text_delta("Two "), text_delta("layers."))
        self.shown("r1")
        self.assertEqual(transport._OPENED_IN_PROMPT, set())

    def test_another_model_keeps_its_live_draft(self):
        self.shown("r1")
        transport.post_stream = streaming(text_delta("Two "), text_delta("layers."))
        self.assertEqual(self.shown("other"), "Two layers.")


class StreamRunnerSourceTest(unittest.TestCase):
    SOURCE = (pathlib.Path(__file__).parent.parent / "ai_agent/core/llm/stream_runner.py").read_text()

    def test_the_request_is_built_the_same_way_as_every_other_one(self):
        self.assertIn("build_network_request", self.SOURCE)

    def test_no_third_party_http_library_sneaks_in(self):
        self.assertNotIn("import requests", self.SOURCE)
        self.assertNotIn("urllib", self.SOURCE)

    def test_the_stream_runs_through_the_shared_exchange_with_an_idle_limit(self):
        self.assertIn("send(request, payload, feedback, on_data=take, idle_timeout_s=timeout)", self.SOURCE)

    def test_stream_request_gets_the_configured_timeout(self):
        call = "build_network_request(endpoint, {**headers, **ACCEPT_HEADER}, verify_override, timeout)"
        self.assertIn(call, self.SOURCE)


class ProviderRequestOptionsTest(unittest.TestCase):
    def test_deepseek_tools_disable_thinking_and_omit_tool_choice(self):
        options = _openai_options("https://api.deepseek.com/v1", SCHEMAS)
        self.assertEqual(options["thinking"], {"type": "disabled"})
        self.assertEqual(options["tools"], SCHEMAS)
        self.assertNotIn("tool_choice", options)

    def test_deepseek_json_protocol_also_disables_thinking(self):
        self.assertEqual(
            _openai_options("https://api.deepseek.com/v1"),
            {"thinking": {"type": "disabled"}},
        )

    def test_other_openai_compatible_hosts_keep_auto_tool_choice(self):
        options = _openai_options("https://api.openai.com/v1", SCHEMAS)
        self.assertEqual(options["tool_choice"], "auto")
        self.assertNotIn("thinking", options)


class ModelWorkerCancellationTest(unittest.TestCase):
    def setUp(self):
        self.saved = worker.call_model
        self.addCleanup(lambda: setattr(worker, "call_model", self.saved))

    def test_every_agent_request_gets_cancellable_feedback(self):
        seen = {}

        def fake(messages, schemas, overrides=None, **options):
            seen.update(overrides or {})
            return ModelTurn(text="done")

        worker.call_model = fake
        thread = worker.ModelTurnThread([], [], {"model_override": "model"})
        thread.run()
        self.assertIn("feedback_override", seen)
        self.assertEqual(seen["model_override"], "model")

    def test_cancel_marks_network_feedback_as_cancelled(self):
        thread = worker.ModelTurnThread([], [], {})
        thread.cancel()
        self.assertTrue(thread._feedback.isCanceled())

    def test_unload_waits_for_threads_left_running_by_an_abort(self):
        from ai_agent.core.agent import turn_thread

        class Thread:
            def __init__(self, finishes):
                self.finishes = finishes
                self.cancelled = False
                self.slots = []
                self.finished = self

            def connect(self, slot):
                self.slots.append(slot)

            def isRunning(self):
                return True

            def cancel(self):
                self.cancelled = True

            def wait(self, timeout):
                return self.finishes

        owner = turn_thread.TurnThreadOwner()
        quick, stuck = Thread(True), Thread(False)
        owner._retired = [quick, stuck]
        owner.stop()
        self.assertTrue(quick.cancelled and stuck.cancelled)
        self.assertIn(stuck, turn_thread._ORPHANS)
        self.assertNotIn(quick, turn_thread._ORPHANS)
        for slot in stuck.slots:
            slot()
        self.assertNotIn(stuck, turn_thread._ORPHANS)

    def test_owner_never_uses_unsafe_qthread_termination(self):
        source = (pathlib.Path(__file__).parent.parent / "ai_agent/core/agent/turn_thread.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(".terminate()", source)
        self.assertIn("self._retired", source)


if __name__ == "__main__":
    unittest.main()
