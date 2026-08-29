import json
import unittest

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.llm import anthropic, transport
from ai_agent.core.llm.stream import consume
from ai_agent.core.llm.thinking import ThinkSplitter, split_thinking
from ai_agent.core.llm.transport import PROTOCOL_JSON, ModelTurn


def event(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def delta(**fields) -> bytes:
    return event({"choices": [{"delta": fields}]})


class SplitterTest(unittest.TestCase):
    def test_plain_text_is_all_visible(self):
        self.assertEqual(split_thinking("just an answer"), ("just an answer", ""))

    def test_a_tagged_block_is_taken_out(self):
        self.assertEqual(split_thinking("<think>musing</think>answer"), ("answer", "musing"))

    def test_text_around_the_block_survives(self):
        visible, thought = split_thinking("before<think>musing</think>after")
        self.assertEqual(visible, "beforeafter")
        self.assertEqual(thought, "musing")

    def test_an_unclosed_block_is_all_thinking(self):
        self.assertEqual(split_thinking("<think>cut off mid"), ("", "cut off mid"))

    def test_several_blocks_are_joined(self):
        visible, thought = split_thinking("<think>one</think>a<think>two</think>b")
        self.assertEqual(visible, "ab")
        self.assertEqual(thought, "onetwo")

    def test_the_thinking_variant_is_recognised(self):
        self.assertEqual(split_thinking("<thinking>x</thinking>y"), ("y", "x"))

    def test_a_tag_split_across_chunks_is_still_found(self):
        splitter = ThinkSplitter()
        self.assertEqual(splitter.feed("<thi"), ("", ""))
        self.assertEqual(splitter.feed("nk>secret"), ("", "secret"))
        self.assertEqual(splitter.feed("</think>said"), ("said", ""))

    def test_a_lone_angle_bracket_is_not_held_forever(self):
        splitter = ThinkSplitter()
        visible, _ = splitter.feed("2 < 3 is true")
        self.assertEqual(visible + splitter.flush()[0], "2 < 3 is true")

    def test_a_closing_tag_split_across_chunks_is_still_found(self):
        splitter = ThinkSplitter()
        splitter.feed("<think>abc")
        self.assertEqual(splitter.feed("</thi"), ("", ""))
        self.assertEqual(splitter.feed("nk>done"), ("done", ""))

    def test_the_partial_tail_comes_out_on_flush(self):
        splitter = ThinkSplitter()
        splitter.feed("answer<thi")
        self.assertEqual(splitter.flush(), ("<thi", ""))


class StreamedThinkingTest(unittest.TestCase):
    def test_a_separate_reasoning_field_is_routed_apart(self):
        seen_text, seen_thought = [], []
        data = consume(
            [delta(reasoning_content="pondering"), delta(content="answer")],
            seen_text.append,
            seen_thought.append,
        )
        self.assertEqual(seen_thought, ["pondering"])
        self.assertEqual(seen_text, ["answer"])
        self.assertEqual(data["choices"][0]["message"]["content"], "answer")
        self.assertEqual(data["choices"][0]["message"]["reasoning_content"], "pondering")

    def test_the_openrouter_spelling_is_also_read(self):
        seen: list[str] = []
        consume([delta(reasoning="pondering")], None, seen.append)
        self.assertEqual(seen, ["pondering"])

    def test_an_inline_tag_never_reaches_the_answer(self):
        seen_text, seen_thought = [], []
        data = consume(
            [delta(content="<think>hmm"), delta(content="mm</think>done")],
            seen_text.append,
            seen_thought.append,
        )
        self.assertEqual("".join(seen_text), "done")
        self.assertEqual("".join(seen_thought), "hmmmm")
        self.assertEqual(data["choices"][0]["message"]["content"], "done")

    def test_both_spellings_at_once_are_not_counted_twice(self):
        seen: list[str] = []
        data = consume([delta(reasoning="The", reasoning_content="The")], None, seen.append)
        self.assertEqual(seen, ["The"])
        self.assertEqual(data["choices"][0]["message"]["reasoning_content"], "The")

    def test_a_null_reasoning_field_is_ignored(self):
        seen: list[str] = []
        consume([delta(reasoning_content=None, content="answer")], None, seen.append)
        self.assertEqual(seen, [])

    def test_an_unclosed_tag_is_flushed_as_thinking_not_as_an_answer(self):
        data = consume([delta(content="<think>never closed")])
        self.assertEqual(data["choices"][0]["message"]["content"], "")
        self.assertEqual(data["choices"][0]["message"]["reasoning_content"], "never closed")


class NativeTurnThinkingTest(unittest.TestCase):
    def test_both_spellings_at_once_are_not_joined_twice(self):
        turn = transport._parse_native_turn(
            {"choices": [{"message": {"content": "answer", "reasoning": "hmm", "reasoning_content": "hmm"}}]}
        )
        self.assertEqual(turn.thinking, "hmm")

    def test_a_reasoning_field_lands_on_the_turn(self):
        turn = transport._parse_native_turn(
            {"choices": [{"message": {"content": "answer", "reasoning_content": "pondering"}}]}
        )
        self.assertEqual(turn.text, "answer")
        self.assertEqual(turn.thinking, "pondering")

    def test_an_inline_tag_is_stripped_out_of_the_answer(self):
        turn = transport._parse_native_turn({"choices": [{"message": {"content": "<think>hmm</think>answer"}}]})
        self.assertEqual(turn.text, "answer")
        self.assertEqual(turn.thinking, "hmm")

    def test_the_json_protocol_reads_past_the_reasoning(self):
        content = '<think>maybe {"tool_calls": [{"name": "wrong"}], "text": "x", "done": true}</think>'
        content += '{"tool_calls": [{"name": "right", "arguments": {}}]}'
        turn = transport._parse_json_turn({"choices": [{"message": {"content": content}}]})
        self.assertEqual([call.name for call in turn.tool_calls], ["right"])
        self.assertEqual(turn.protocol, PROTOCOL_JSON)
        self.assertIn("maybe", turn.thinking)


class AnthropicThinkingTest(unittest.TestCase):
    BLOCKS = [
        {"type": "thinking", "thinking": "pondering", "signature": "sig-1"},
        {"type": "text", "text": "answer"},
    ]

    def test_thinking_is_off_unless_a_budget_is_set(self):
        self.assertNotIn("thinking", anthropic.build_body([], [], "claude"))

    def test_a_budget_below_the_minimum_is_not_sent(self):
        body = anthropic.build_body([], [], "claude", thinking_budget=100)
        self.assertNotIn("thinking", body)

    def test_a_real_budget_is_requested(self):
        body = anthropic.build_body([], [], "claude", thinking_budget=2048)
        self.assertEqual(body["thinking"], {"type": "enabled", "budget_tokens": 2048})

    def test_the_answer_still_fits_above_the_budget(self):
        body = anthropic.build_body([], [], "claude", thinking_budget=8192)
        self.assertGreater(body["max_tokens"], 8192)

    def test_blocks_are_parsed_out_with_their_signature(self):
        text, blocks = anthropic.parse_thinking({"content": self.BLOCKS})
        self.assertEqual(text, "pondering")
        self.assertEqual(blocks[0]["signature"], "sig-1")

    def test_redacted_blocks_are_kept_even_without_readable_text(self):
        _, blocks = anthropic.parse_thinking({"content": [{"type": "redacted_thinking", "data": "opaque"}]})
        self.assertEqual(len(blocks), 1)

    def test_thinking_does_not_leak_into_the_visible_answer(self):
        text, _, _ = anthropic.parse_response({"content": self.BLOCKS})
        self.assertEqual(text, "answer")

    def test_blocks_come_back_first_in_the_assistant_turn(self):
        message = {
            "role": "assistant",
            "content": "answer",
            "thinking_blocks": [{"type": "thinking", "thinking": "x", "signature": "s"}],
            "tool_calls": [{"id": "c1", "function": {"name": "list_layers", "arguments": "{}"}}],
        }
        translated = anthropic.translate_message(message)
        self.assertEqual([block["type"] for block in translated["content"]], ["thinking", "text", "tool_use"])

    def test_blocks_are_not_sent_back_when_thinking_is_off(self):
        messages = [
            {
                "role": "assistant",
                "content": "answer",
                "thinking_blocks": [{"type": "thinking", "thinking": "x", "signature": "s"}],
            }
        ]
        body = anthropic.build_body(messages, [], "claude")
        self.assertEqual([block["type"] for block in body["messages"][0]["content"]], ["text"])

    def test_blocks_are_sent_back_when_thinking_is_on(self):
        messages = [
            {
                "role": "assistant",
                "content": "answer",
                "thinking_blocks": [{"type": "thinking", "thinking": "x", "signature": "s"}],
            }
        ]
        body = anthropic.build_body(messages, [], "claude", thinking_budget=2048)
        self.assertEqual([block["type"] for block in body["messages"][0]["content"]], ["thinking", "text"])

    def test_a_budget_too_small_to_request_also_drops_the_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": "answer",
                "thinking_blocks": [{"type": "thinking", "thinking": "x"}],
            }
        ]
        body = anthropic.build_body(messages, [], "claude", thinking_budget=100)
        self.assertEqual([block["type"] for block in body["messages"][0]["content"]], ["text"])

    def test_an_empty_turn_stays_dropped(self):
        self.assertIsNone(
            anthropic.translate_message(
                {"role": "assistant", "thinking_blocks": [{"type": "thinking", "thinking": "x"}]}
            )
        )


class LoopThinkingTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.seen: list[str] = []
        self.loop.thinking_chunk.connect(self.seen.append)

    def test_streamed_reasoning_is_passed_on(self):
        self.loop._on_thinking("pondering")
        self.assertEqual(self.seen, ["pondering"])

    def test_a_turn_that_never_streamed_replays_its_reasoning_once(self):
        self.loop._streamed_thinking = False
        self.loop._replay_thinking(ModelTurn(thinking="arrived whole"))
        self.assertEqual(self.seen, ["arrived whole"])

    def test_what_already_streamed_is_not_shown_twice(self):
        self.loop._on_thinking("live")
        self.loop._replay_thinking(ModelTurn(thinking="live"))
        self.assertEqual(self.seen, ["live"])

    def test_a_turn_without_reasoning_says_nothing(self):
        self.loop._streamed_thinking = False
        self.loop._replay_thinking(ModelTurn(text="answer"))
        self.assertEqual(self.seen, [])

    def test_an_aborted_run_stops_reporting(self):
        self.loop._aborted = True
        self.loop._on_thinking("too late")
        self.assertEqual(self.seen, [])


class TranscriptThinkingTest(unittest.TestCase):
    def test_the_reasoning_text_is_never_sent_back(self):
        transcript = Transcript()
        transcript.add_turn(ModelTurn(text="answer", thinking="a long private monologue"))
        rendered = json.dumps(transcript.build_messages("system"))
        self.assertNotIn("private monologue", rendered)

    def test_anthropic_blocks_are_carried_for_the_round_trip(self):
        transcript = Transcript()
        blocks = [{"type": "thinking", "thinking": "x", "signature": "sig"}]
        transcript.add_turn(ModelTurn(text="answer", thinking_blocks=blocks))
        message = transcript.build_messages("system")[-1]
        self.assertEqual(message["thinking_blocks"], blocks)

    def test_nothing_extra_is_added_without_blocks(self):
        transcript = Transcript()
        transcript.add_turn(ModelTurn(text="answer"))
        self.assertNotIn("thinking_blocks", transcript.build_messages("system")[-1])


if __name__ == "__main__":
    unittest.main()
