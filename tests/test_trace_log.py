import json
import shutil
import tempfile
import unittest

from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.store import SessionStore
from ai_agent.core.state.trace import APPLIED, CALL, PENDING, PLAN_ROLE, THOUGHT, TRACE_ROLE, TraceLog
from ai_agent.qgis_tools.call_summary import CallSummary


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class TraceLogTest(unittest.TestCase):
    """A turn's steps as they happened, handed over once and then forgotten."""

    def setUp(self):
        self.clock = Clock()
        self.log = TraceLog(self.clock)

    def test_a_call_keeps_its_words_values_skill_result_and_time(self):
        summary = CallSummary.marking("Reading layer 'roads'", {"layer_name": "roads"})
        summary.skill = "inspect"
        self.log.call(summary)
        self.clock.now += 1.25
        self.log.finished(True, "12 features")
        record = self.log.take()
        step = record["steps"][0]
        self.assertEqual(step["kind"], CALL)
        self.assertEqual(step["text"], "Reading layer 'roads'")
        self.assertIn(["roads", True], step["parts"])
        self.assertEqual(
            (step["skill"], step["ok"], step["note"], step["seconds"]), ("inspect", True, "12 features", 1.25)
        )
        self.assertEqual(record["seconds"], 1.25)
        self.assertIsNone(self.log.take(), "a handed-over turn is not handed over twice")

    def test_reasoning_that_streamed_has_a_time_and_one_that_came_whole_has_none(self):
        self.log.thinking("first ")
        self.clock.now += 2
        self.log.thinking("second")
        self.log.done("Using style")
        self.log.thinking("whole")
        steps = self.log.take()["steps"]
        self.assertEqual([step["kind"] for step in steps], [THOUGHT, CALL, THOUGHT])
        self.assertEqual((steps[0]["text"], steps[0]["seconds"]), ("first second", 2))
        self.assertIsNone(steps[2]["seconds"])
        self.assertNotIn("_started", json.dumps(steps))

    def test_a_cut_short_call_and_a_rejected_one_are_kept_as_they_ended(self):
        self.log.rejected("Rejected: delete")
        self.log.call("Downloading roads")
        steps = self.log.take()["steps"]
        self.assertEqual((steps[0]["ok"], steps[0]["rejected"]), (False, True))
        self.assertEqual((steps[1]["ok"], steps[1]["seconds"]), (None, None))


class DisplayEntriesTest(unittest.TestCase):
    """The trace and plan cards are saved for the chat and never reach the model."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = ConversationState(store=SessionStore(self.root))

    def test_the_turns_steps_are_written_before_the_answer_and_stay_out_of_the_window(self):
        self.state.add("user", "Which layers?")
        self.state.trace.thinking("Let me look.")
        self.state.trace.done("Using inspect")
        self.state.add("assistant", "Three layers.")
        roles = [message["role"] for message in self.state.messages]
        self.assertEqual(roles, ["user", TRACE_ROLE, "assistant"])
        self.assertEqual([message["role"] for message in self.state.window()], ["user", "assistant"])
        shown = self.state.replayable()
        self.assertEqual(shown[1]["trace"]["steps"][0]["text"], "Let me look.")

    def test_a_plan_card_is_kept_and_settled_by_its_key(self):
        self.state.add("user", "Colour the rivers")
        key = self.state.add_plan(["Styling 'rivers' blue"])
        self.assertEqual(self.state.replayable()[-1]["plan"]["state"], PENDING)
        self.state.update_plan(key, state=APPLIED, at="14:32", marks=[["done", ""]])
        plan = self.state.replayable()[-1]["plan"]
        self.assertEqual((plan["state"], plan["at"], plan["lines"]), (APPLIED, "14:32", ["Styling 'rivers' blue"]))
        self.assertTrue(all(message["role"] != PLAN_ROLE for message in self.state.window()))

    def test_a_picked_answer_is_flagged_for_the_chat_but_the_model_gets_role_and_content_only(self):
        self.state.add("user", "pop2020", chosen=True)
        self.assertTrue(self.state.replayable()[-1]["chosen"])
        self.assertEqual(self.state.window()[-1], {"role": "user", "content": "pop2020"})

    def test_switching_conversations_keeps_the_trace_with_the_old_one_and_deleting_drops_it(self):
        self.state.add("user", "first")
        self.state.trace.done("Using inspect")
        old = self.state.session_identifier
        self.state.start_new()
        reopened = ConversationState(store=SessionStore(self.root))
        self.assertTrue(reopened.restore(old))
        self.assertEqual(reopened.messages[-1]["role"], TRACE_ROLE)
        self.state.add("user", "second")
        self.state.trace.done("Using style")
        self.state.delete(self.state.session_identifier)
        self.assertIsNone(self.state.trace.take())


if __name__ == "__main__":
    unittest.main()
