import unittest

from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent import notices
from ai_agent.core.agent.announcements import announces_a_step
from ai_agent.core.agent.batch import MODEL_LINE_LIMIT, _model_line
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ModelTurn, ToolCall
from ai_agent.skills.registry import SKILL_REGISTRY


class _Request:
    messages: list = []
    tool_schemas: list = []
    overrides: dict = {}
    protocol = "native"


class ModelLineTest(unittest.TestCase):
    def test_the_line_names_the_tool_and_public_arguments(self):
        call = ToolCall(id="c", name="set_opacity", arguments={"layer_name": "roads", "opacity": 0.5, "_pin": "x"})
        self.assertEqual(_model_line(call), 'set_opacity {"layer_name": "roads", "opacity": 0.5}')

    def test_long_arguments_are_cut(self):
        call = ToolCall(id="c", name="run_python", arguments={"code": "x" * 1000})
        self.assertEqual(len(_model_line(call)), MODEL_LINE_LIMIT)


class DuplicateCallTest(unittest.TestCase):
    def test_a_repeated_call_is_answered_as_a_duplicate(self):
        loop = AgentLoop()
        loop._loaded_skills = ["inspect", "project"]
        queued = []
        loop.tool_queued.connect(queued.append)
        first = loop._dispatch(ToolCall(id="a", name="remember", arguments={"note": "POP is census 2020"}))
        second = loop._dispatch(ToolCall(id="b", name="remember", arguments={"note": "POP is census 2020"}))
        self.assertEqual(first.payload["status"], "queued")
        self.assertNotIn("duplicate", first.payload)
        self.assertTrue(second.payload.get("duplicate"))
        self.assertEqual(second.payload["status"], "queued")
        self.assertEqual(len(queued), 1)
        self.assertEqual(len(loop.pending_writes()), 1)


class NudgeTest(unittest.TestCase):
    def setUp(self):
        self.saved = loop_module.build_step_request
        loop_module.build_step_request = lambda *args, **kwargs: _Request()
        self.loop = AgentLoop()
        self.loop._turn.start = lambda *args: None
        self.finished = []
        self.kept = []
        self.loop.finished.connect(self.finished.append)
        self.loop.preamble.connect(self.kept.append)
        self.loop.start("task", [])

    def tearDown(self):
        loop_module.build_step_request = self.saved
        self.loop.abort()

    def last_user_text(self):
        users = [entry["text"] for entry in self.loop._transcript.entries if entry["kind"] == "user"]
        return users[-1]

    def test_a_cut_off_answer_gets_one_more_turn(self):
        self.loop._on_turn(ModelTurn(text="Half of the", finish_reason="length"))
        self.assertEqual(self.finished, [])
        self.assertEqual(self.kept, ["Half of the"])
        self.assertEqual(self.last_user_text(), notices.CONTINUE_TRUNCATED)
        self.loop._on_turn(ModelTurn(text="rest.", finish_reason="length"))
        self.assertEqual(self.finished, ["rest."])

    def test_an_empty_answer_gets_one_more_turn(self):
        self.loop._on_turn(ModelTurn(text=""))
        self.assertEqual(self.finished, [])
        self.assertEqual(self.last_user_text(), notices.EMPTY_REPLY)

    def test_a_normal_answer_ends_the_run(self):
        self.loop._on_turn(ModelTurn(text="Done.", finish_reason="stop"))
        self.assertEqual(self.finished, ["Done."])

    def test_a_first_reply_that_only_announces_a_step_gets_one_more_turn(self):
        self.loop._on_turn(ModelTurn(text="This is an export, so I'll load the export tool.", finish_reason="stop"))
        self.assertEqual(self.finished, [])
        self.assertEqual(self.last_user_text(), notices.ANNOUNCED_STEP)
        self.loop._on_turn(ModelTurn(text="Let me load it.", finish_reason="stop"))
        self.assertEqual(self.finished, ["Let me load it."], "the nudge is given once")

    def test_after_real_work_an_offer_ends_the_run(self):
        call = ToolCall(id="c", name="list_layers", arguments={})
        self.loop._dispatch = lambda tool_call: ToolResult(call=tool_call, payload={"layers": []})
        self.loop._on_turn(ModelTurn(text="", tool_calls=[call]))
        self.loop._on_turn(ModelTurn(text="Done. I'll save the project if you like.", finish_reason="stop"))
        self.assertEqual(self.finished, ["Done. I'll save the project if you like."])


class AnnouncementTest(unittest.TestCase):
    def test_a_short_reply_announcing_its_next_step(self):
        for text in ("I'll load the export tool.", "Let me check the layer first.", "Now I need the processing skill."):
            with self.subTest(text):
                self.assertTrue(announces_a_step(text))

    def test_answers_offers_questions_and_long_texts_are_not(self):
        for text in (
            "Two layers.",
            "Let me know if you want labels.",
            "Shall I save the project?",
            "Which layer？",
            "I'll explain. " + "A projection flattens the Earth. " * 20,
            "",
        ):
            with self.subTest(text):
                self.assertFalse(announces_a_step(text))


class SkillDescriptionTest(unittest.TestCase):
    def test_common_requests_find_their_skill_by_description(self):
        expectations = {
            "processing": "heatmap",
            "style": "label",
            "project": "undo",
            "layout": "north arrow",
            "web": "geocoding",
        }
        for skill, word in expectations.items():
            with self.subTest(skill=skill):
                self.assertIn(word, SKILL_REGISTRY.get(skill).description.lower())


if __name__ == "__main__":
    unittest.main()
