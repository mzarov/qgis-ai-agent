import json
import unittest

from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent import prompts, request
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import COMPACT_STEP, KEEP_FULL_RESULTS, ToolResult, Transcript
from ai_agent.core.llm import anthropic
from ai_agent.core.llm.live import LIVE_KEY, fold_live, live_message, split_live
from ai_agent.core.llm.turns import ModelTurn, ToolCall

OVERRIDES = {"url_override": "https://api.example/v1"}
SYSTEM = {"role": "system", "content": "rules"}


class FoldLiveTest(unittest.TestCase):
    def test_without_a_state_message_nothing_changes(self):
        messages = [SYSTEM, {"role": "user", "content": "hi"}]
        self.assertEqual(fold_live(messages), messages)

    def test_the_state_joins_the_last_user_message(self):
        folded = fold_live([SYSTEM, {"role": "user", "content": "hi"}, live_message("state")])
        self.assertEqual(folded[-1], {"role": "user", "content": "hi\n\nstate"})
        self.assertEqual(len(folded), 2)

    def test_the_state_joins_a_tool_result_instead_of_following_it(self):
        tool = {"role": "tool", "tool_call_id": "c1", "content": "{}"}
        folded = fold_live([SYSTEM, tool, live_message("state")])
        self.assertEqual(folded[-1]["role"], "tool")
        self.assertEqual(folded[-1]["tool_call_id"], "c1")
        self.assertTrue(folded[-1]["content"].endswith("state"))

    def test_the_state_joins_an_image_message_as_a_text_part(self):
        image = {"role": "user", "content": [{"type": "text", "text": "look"}]}
        folded = fold_live([SYSTEM, image, live_message("state")])
        self.assertEqual(folded[-1]["content"][-1], {"type": "text", "text": "state"})

    def test_after_an_assistant_message_the_state_becomes_a_user_message(self):
        folded = fold_live([SYSTEM, {"role": "assistant", "content": "ok"}, live_message("state")])
        self.assertEqual(folded[-1], {"role": "user", "content": "state"})

    def test_the_marker_never_reaches_the_endpoint(self):
        folded = fold_live([SYSTEM, {"role": "user", "content": "hi"}, live_message("state")])
        self.assertNotIn(LIVE_KEY, json.dumps(folded))

    def test_split_returns_the_state_text(self):
        rest, live = split_live([SYSTEM, live_message("state")])
        self.assertEqual((rest, live), ([SYSTEM], "state"))


class AnthropicLiveStateTest(unittest.TestCase):
    def test_the_state_follows_the_cache_breakpoint(self):
        tool = {"role": "tool", "tool_call_id": "c1", "content": "{}"}
        body = anthropic.build_body([SYSTEM, tool, live_message("state")], [], "claude-x", cache_prefix_chars=5)
        blocks = body["messages"][-1]["content"]
        self.assertEqual(blocks[0]["type"], "tool_result")
        self.assertIn("cache_control", blocks[0])
        self.assertEqual(blocks[-1], {"type": "text", "text": "state"})
        self.assertEqual(len(body["messages"]), 1)

    def test_without_caching_the_state_is_still_sent(self):
        body = anthropic.build_body([SYSTEM, {"role": "user", "content": "hi"}, live_message("state")], [], "c")
        self.assertEqual(body["messages"][-1]["content"][-1]["text"], "state")
        self.assertNotIn(LIVE_KEY, json.dumps(body))


class StableSystemPromptTest(unittest.TestCase):
    def setUp(self):
        self.saved = request.get_project_context, request._project_notes
        request._project_notes = lambda: ""

    def tearDown(self):
        request.get_project_context, request._project_notes = self.saved

    def build(self, context, queued, plan):
        request.get_project_context = lambda: context
        transcript = Transcript()
        transcript.add_user("task")
        return request.build_step_request(transcript, ["inspect"], [], dict(OVERRIDES), plan, queued)

    def test_the_system_prompt_does_not_change_while_the_run_moves(self):
        first = self.build("Layers: a.", "", "")
        later = self.build(
            "Layers: a, b.",
            prompts.render_queued_steps(["Colour roads"]),
            prompts.render_task_plan(["x", "y", "z"], 1),
        )
        self.assertEqual(first.messages[0], later.messages[0])
        self.assertEqual(later.overrides[anthropic.CACHE_PREFIX_KEY], len(later.messages[0]["content"]))

    def test_the_moving_parts_arrive_last_as_a_state_message(self):
        built = self.build("Layers: roads.", prompts.render_queued_steps(["Colour roads"]), "")
        state = built.messages[-1]
        self.assertTrue(state.get(LIVE_KEY))
        self.assertIn(prompts.LIVE_STATE_HEADER, state["content"])
        self.assertIn("Layers: roads.", state["content"])
        self.assertIn("Colour roads", state["content"])
        self.assertNotIn("Layers: roads.", built.messages[0]["content"])

    def test_an_empty_state_adds_no_message(self):
        built = self.build("", "", "")
        self.assertFalse(built.messages[-1].get(LIVE_KEY))


class SteppedCompactionTest(unittest.TestCase):
    @staticmethod
    def rendered(rounds):
        transcript = Transcript()
        transcript.add_user("task")
        for index in range(rounds):
            call = ToolCall(id=f"c{index}", name="list_layers", arguments={})
            transcript.add_turn(ModelTurn(tool_calls=[call]))
            transcript.add_results([ToolResult(call=call, payload={"data": "x" * 3000})], "native")
        return [message["content"] for message in transcript.build_messages("sys") if message["role"] == "tool"]

    def test_older_results_keep_their_text_between_steps(self):
        base = KEEP_FULL_RESULTS + COMPACT_STEP
        for rounds in range(base, base + COMPACT_STEP - 1):
            shorter, longer = self.rendered(rounds), self.rendered(rounds + 1)
            self.assertEqual(longer[: len(shorter)], shorter)

    def test_the_boundary_moves_a_whole_step_at_once(self):
        compacted = [sum("compacted" in text for text in self.rendered(rounds)) for rounds in range(1, 20)]
        self.assertEqual(sorted(set(compacted)), [0, COMPACT_STEP, 2 * COMPACT_STEP, 3 * COMPACT_STEP])

    def test_the_newest_results_always_stay_full(self):
        for rounds in range(1, 20):
            fresh = self.rendered(rounds)[-KEEP_FULL_RESULTS:]
            self.assertFalse(any("compacted" in text for text in fresh))


class PreloadTest(unittest.TestCase):
    def setUp(self):
        self.saved = loop_module.build_step_request
        self.requests = []
        loop_module.build_step_request = lambda *args, **kwargs: self.requests.append((args, kwargs)) or _Request()
        self.loop = AgentLoop()
        self.loop._turn.start = lambda *args: None

    def tearDown(self):
        loop_module.build_step_request = self.saved
        self.loop.abort()

    def test_preloaded_skills_are_loaded_without_claiming_the_user_invoked_them(self):
        self.loop.start("check", [], verification=True, preload=["style"])
        self.assertIn("style", self.loop.loaded_skills)
        args, kwargs = self.requests[-1]
        self.assertIn("style", args[1])
        self.assertEqual(list(kwargs.get("invoked_skills") or []), [])

    def test_unknown_preloaded_names_are_ignored(self):
        self.loop.start("check", [], preload=["nope"])
        self.assertNotIn("nope", self.loop.loaded_skills)


class MeasurementTest(unittest.TestCase):
    def test_the_replayed_task_stays_cheap(self):
        from tools import measure_tokens

        numbers = measure_tokens.measure()
        self.assertLess(numbers["uncached"], numbers["sent"] / 4)
        self.assertLess(numbers["uncached"], 30_000)


class _Request:
    messages: list = []
    tool_schemas: list = []
    overrides: dict = {}
    protocol = "native"


if __name__ == "__main__":
    unittest.main()
