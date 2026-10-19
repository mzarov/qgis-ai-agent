import json
import shutil
import tempfile
import unittest
from unittest import mock

from ai_agent.core.orchestrator import notices
from ai_agent.core.orchestrator import orchestrator as orchestrator_module
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.store import SessionStore
from ai_agent.core.state.trace import TRACE_ROLE
from tests.test_orchestrator import Agent, Call, Iface, Result, StepDock

NOTHING_TO_APPLY = "There are no changes to apply."


class FeedDock(StepDock):
    def __init__(self):
        super().__init__()
        self.done_rows = []
        self.rejected_rows = []
        self.results = []
        self.streamed = None
        self.restored = []
        self.retry_offers = 0

    def mark_tool_done(self, message_id, ok=True, note=""):
        self.done_rows.append((message_id, ok))

    def add_rejected_message(self, text):
        self.rejected_rows.append(str(text))
        return 1

    def add_result_message(self, text):
        self.results.append(text)
        return 1

    def finish_stream(self, markdown):
        return markdown == self.streamed

    def restore_prompt(self, text):
        self.restored.append(text)

    def offer_retry(self):
        self.retry_offers += 1


class OrchestratorCase(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.dock = FeedDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.store = SessionStore(root)
        self.orchestrator.conversation = ConversationState(store=self.store)
        self.agent = self.orchestrator.agent = Agent()
        self.compaction = self.orchestrator.compaction = mock.MagicMock(is_running=False)
        self.compaction.needed.return_value = False

    @property
    def messages(self):
        return self.orchestrator.conversation.messages

    def contents(self, role):
        return [message["content"] for message in self.messages if message["role"] == role]


class RequestGuardsTest(OrchestratorCase):
    def test_a_request_while_the_conversation_compacts_waits(self):
        self.compaction.is_running = True
        self.orchestrator.on_prompt("Colour the rivers")
        self.assertIsNone(self.agent.started)
        self.assertEqual(self.messages, [])
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)

    def test_a_request_whose_compaction_is_stopped_is_kept_but_not_sent(self):
        self.compaction.needed.return_value = True
        self.compaction.start.side_effect = lambda after, cancelled: cancelled() or True
        self.orchestrator.on_prompt("Colour the rivers")
        self.assertIsNone(self.agent.started)
        self.assertEqual(self.contents("user"), ["Colour the rivers"])

    def test_a_request_waits_for_its_compaction_and_then_goes(self):
        waiting = []
        self.compaction.needed.return_value = True
        self.compaction.start.side_effect = lambda after, cancelled: waiting.append(after) or True
        self.orchestrator.on_prompt("Colour the rivers")
        self.assertIsNone(self.agent.started)
        waiting[0]()
        self.assertEqual(self.agent.started, ("Colour the rivers", []))

    def test_an_interjection_the_run_cannot_take_is_refused_and_not_saved(self):
        self.agent.is_running = True
        self.agent.interject = lambda text: False
        self.orchestrator.on_prompt("blue, not red")
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)
        self.assertEqual(self.messages, [])

    def test_an_answer_to_a_remote_model_waits_for_consent(self):
        self.agent.is_awaiting_answer = True
        self.agent.endpoint = "https://provider.example/v1"
        self.dock.confirm_data_sharing = lambda endpoint: False
        with (
            mock.patch.object(orchestrator_module, "_is_configured", return_value=True),
            mock.patch.object(orchestrator_module, "get_data_sharing_consent", return_value=False),
        ):
            self.orchestrator.on_prompt("roads")
        self.assertIsNone(self.agent.answered)
        self.assertEqual(self.messages, [])
        self.assertIn(notices.DATA_SHARING_DECLINED, self.dock.system)


class RetryAndCompactTest(OrchestratorCase):
    def test_retry_while_busy_waits_and_retry_with_nothing_failed_does_nothing(self):
        self.orchestrator.on_retry()
        self.assertIsNone(self.agent.started)
        self.assertEqual(self.dock.system, [])
        self.orchestrator.on_prompt("Colour the rivers")
        self.orchestrator.on_failed("HTTP 500")
        self.agent.started = None
        self.agent.is_running = True
        self.orchestrator.on_retry()
        self.assertIsNone(self.agent.started)
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)

    def test_saved_settings_offer_retry_only_when_idle(self):
        self.orchestrator.on_prompt("Colour the rivers")
        self.orchestrator.on_failed("HTTP 401")
        self.agent.is_running = True
        self.orchestrator.on_settings_saved()
        self.assertEqual(self.dock.retry_offers, 0)
        self.agent.is_running = False
        self.orchestrator.on_settings_saved()
        self.assertEqual(self.dock.retry_offers, 1)

    def test_compacting_by_hand_starts_when_idle_and_waits_when_busy(self):
        self.agent.is_running = True
        self.orchestrator.on_compact()
        self.compaction.start.assert_not_called()
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)
        self.agent.is_running = False
        self.orchestrator.on_compact()
        self.compaction.start.assert_called_once_with()

    def test_a_counted_turn_measures_the_window_and_refreshes_the_meter(self):
        self.orchestrator.on_turn_counted(1200, 80, True)
        self.orchestrator.on_turn_counted(1500, 20, False)
        session = self.orchestrator.conversation._session
        self.assertEqual((session.context_tokens, session.spent_tokens, session.requests), (1200, 2800, 2))
        self.assertEqual(self.compaction.refresh.call_count, 2)


class FeedEventsTest(OrchestratorCase):
    def test_a_step_stopped_mid_run_is_drawn_and_saved_as_failed(self):
        self.orchestrator.on_prompt("Describe roads")
        self.orchestrator.on_tool_started("Reading layer roads")
        self.orchestrator.on_aborted()
        self.assertEqual(self.dock.done_rows, [(1, False)])
        traces = [json.loads(message["content"]) for message in self.messages if message["role"] == TRACE_ROLE]
        self.assertEqual([step["ok"] for step in traces[-1]["steps"]], [False])
        self.assertIn(notices.RUN_STOPPED, self.dock.system)

    def test_a_step_that_ends_after_its_row_was_closed_marks_nothing(self):
        self.orchestrator.on_tool_finished("list_layers", True)
        self.assertEqual(self.dock.done_rows, [])

    def test_an_empty_answer_says_so_and_saves_nothing(self):
        self.orchestrator.on_finished("   ")
        self.assertEqual((self.messages, self.dock.results), ([], []))
        self.assertIn("The model returned nothing. Try rephrasing.", self.dock.system)

    def test_a_streamed_answer_is_finished_in_place_not_drawn_twice(self):
        self.dock.streamed = "Two layers."
        self.orchestrator.on_finished("Two layers.")
        self.assertEqual(self.dock.results, [])
        self.assertEqual(self.contents("assistant"), ["Two layers."])

    def test_a_rejected_call_is_drawn_and_kept_in_the_trace(self):
        self.orchestrator.on_tool_rejected("Setting opacity of roads")
        self.assertEqual(self.dock.rejected_rows, ["Rejected: Setting opacity of roads"])
        self.orchestrator.conversation.keep_trace()
        steps = json.loads(self.messages[-1]["content"])["steps"]
        self.assertEqual([(step["ok"], step.get("rejected")) for step in steps], [(False, True)])

    def test_the_task_plan_shows_its_done_steps(self):
        self.orchestrator.on_plan_changed(["Load roads", "Buffer", "Style"], 1)
        self.assertEqual(self.dock.tool_rows, ["Plan 1/3: ✓ Load roads · Buffer · Style"])

    def test_a_written_journal_is_named(self):
        self.orchestrator.on_journal_written("/tmp/run_1.md")
        self.assertIn("Run journal: /tmp/run_1.md", self.dock.system)


class PlanCardTest(OrchestratorCase):
    def test_the_last_words_come_before_the_card_and_are_saved(self):
        self.orchestrator.on_confirm_needed([Call()], "I will colour the rivers blue.")
        self.assertEqual(self.dock.results, ["I will colour the rivers blue."])
        self.assertEqual(self.contents("assistant"), ["I will colour the rivers blue."])
        self.assertEqual(self.dock.plan_lines and len(self.dock.plan_lines), 1)

    def test_apply_with_nothing_queued_or_during_compaction_does_nothing(self):
        self.orchestrator.on_confirm_plan()
        self.assertIn(NOTHING_TO_APPLY, self.dock.system)
        self.agent.has_pending_writes = True
        self.compaction.is_running = True
        self.orchestrator.on_confirm_plan()
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)
        self.assertFalse(getattr(self.agent, "confirmed", False))

    def test_a_mode_switch_during_a_run_applies_from_the_next_request(self):
        with mock.patch("ai_agent.core.orchestrator.plans.set_work_mode") as saved:
            self.agent.is_running = True
            self.orchestrator.on_work_mode("auto")
            self.agent.is_running = False
            self.orchestrator.on_work_mode("ask")
        self.assertEqual([item.args for item in saved.call_args_list], [("auto",), ("ask",)])
        self.assertEqual(self.dock.system.count(notices.MODE_NEXT_REQUEST), 1)

    def test_cancel_without_a_card_still_declines_the_plan(self):
        self.orchestrator.on_cancel_plan()
        self.assertTrue(self.agent.cancelled)
        self.assertEqual(self.dock.cancelled_plans, [])

    def test_a_step_done_during_apply_is_not_redrawn_at_the_end(self):
        self.orchestrator.on_confirm_needed([Call("set_opacity"), Call("set_symbol")], "")
        self.agent.is_applying = True
        self.orchestrator.on_tool_started("Opacity of roads")
        self.orchestrator.on_tool_finished("set_opacity", True)
        self.agent.is_applying = False
        self.orchestrator.on_applied([Result(name="set_opacity"), Result(name="set_symbol")])
        self.assertEqual([index for index, _state, _note in self.dock.steps], [0, 0, 1])


class SessionsTest(OrchestratorCase):
    def setUp(self):
        super().setUp()
        self.orchestrator.on_prompt("first question")
        self.orchestrator.on_finished("first answer")
        self.first = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_prompt("second question")
        self.second = self.orchestrator.conversation.session_identifier

    def test_nothing_is_opened_or_deleted_while_a_plan_applies(self):
        self.agent.is_applying = True
        self.orchestrator.on_session_chosen(self.first)
        self.orchestrator.on_session_deleted(self.second)
        self.assertEqual(self.orchestrator.conversation.session_identifier, self.second)
        self.assertIsNotNone(self.store.load(self.second))
        self.assertEqual(self.dock.system.count(notices.SWITCH_WHILE_APPLYING), 2)

    def test_deleting_the_current_conversation_stops_its_run(self):
        self.agent.is_running = True
        self.orchestrator.on_session_deleted(self.second)
        self.assertEqual(self.agent.aborts, 1)
        self.assertIsNone(self.store.load(self.second))
        self.assertEqual(self.dock.replayed, [])

    def test_deleting_another_conversation_leaves_the_run_alone(self):
        self.agent.is_running = True
        self.orchestrator.on_session_deleted(self.first)
        self.assertEqual(self.agent.aborts, 0)
        self.assertIsNone(self.store.load(self.first))
        self.assertEqual(self.contents("user"), ["second question"])

    def test_renaming_another_conversation_keeps_the_title(self):
        titles = []
        self.dock.set_conversation_title = titles.append
        self.orchestrator.on_session_renamed(self.first, "Old one")
        self.assertEqual(titles, [])
        self.assertEqual(self.store.load(self.first).title, "Old one")

    def test_erasing_the_history_deletes_the_current_conversation(self):
        self.orchestrator.on_history_erased()
        self.assertIsNone(self.store.load(self.second))
        self.assertEqual(self.dock.replayed, [])


if __name__ == "__main__":
    unittest.main()
