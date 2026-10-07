import pathlib
import unittest
from unittest import mock

from ai_agent.qgis_tools.call_summary import CallSummary
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.messages import AssistantMessage
from ai_agent.ui.thinking import ThinkingBlock

DOCK_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "dock_widget.py").read_text(
    encoding="utf-8"
)


class DraftTest(unittest.TestCase):
    def setUp(self):
        self.view = ConversationView()

    def test_the_first_delta_opens_a_draft(self):
        self.view.append_draft("Hel")
        self.assertIsNotNone(self.view._draft)

    def test_later_deltas_grow_the_same_draft(self):
        self.view.append_draft("Hel")
        first = self.view._draft
        self.view.append_draft("lo")
        self.assertIs(self.view._draft, first)
        self.assertEqual(first._markdown, "Hello")

    def test_finishing_replaces_the_text_and_closes_the_draft(self):
        self.view.append_draft("Hel")
        draft = self.view._draft
        self.assertTrue(self.view.finish_draft("**Hello**"))
        self.assertIsNone(self.view._draft)
        self.assertEqual(draft._markdown, "**Hello**")

    def test_finishing_without_a_draft_reports_it(self):
        self.assertFalse(self.view.finish_draft("Hello"))

    def test_a_tool_call_drops_the_preamble(self):
        self.view.append_draft("let me look")
        self.view.add_activity_step("Reading the project.")
        self.assertIsNone(self.view._draft)

    def test_any_other_message_drops_the_preamble(self):
        self.view.append_draft("let me look")
        self.view.add_system_message("Run stopped.")
        self.assertIsNone(self.view._draft)

    def test_a_dropped_draft_is_not_reused(self):
        self.view.append_draft("first")
        dropped = self.view._draft
        self.view.add_activity_step("Reading the project.")
        self.view.append_draft("second")
        self.assertIsNot(self.view._draft, dropped)
        self.assertEqual(self.view._draft._markdown, "second")

    def test_clearing_forgets_the_draft(self):
        self.view.append_draft("half a")
        self.view.clear()
        self.assertIsNone(self.view._draft)

    def test_delayed_autoscroll_respects_a_user_who_scrolled_up(self):
        scrolled = []
        self.view._pinned = False
        self.view._scroll_to_bottom = lambda: scrolled.append(True)
        self.view._scroll_if_still_pinned()
        self.assertEqual(scrolled, [])


class DockHeaderContractTest(unittest.TestCase):
    def test_header_starts_a_real_new_conversation(self):
        self.assertIn('tr("New conversation"), self.new_session_clicked.emit', DOCK_SOURCE)
        self.assertNotIn("def _on_clear", DOCK_SOURCE)


class WelcomeFeedTest(unittest.TestCase):
    def setUp(self):
        self.view = ConversationView()

    def test_an_empty_feed_shows_the_welcome_card(self):
        self.assertIsNotNone(self.view._empty)

    def test_the_first_message_replaces_it(self):
        welcome = self.view._empty
        self.view.add_user_message("hello")
        self.assertIsNone(self.view._empty)
        # Hidden at once, not only scheduled for deletion: a busy main thread painted it over the chat.
        self.assertTrue(welcome.isHidden())

    def test_a_streamed_answer_also_replaces_it(self):
        self.view.append_draft("hi")
        self.assertIsNone(self.view._empty)

    def test_clearing_brings_it_back(self):
        self.view.add_user_message("hello")
        self.view.clear()
        self.assertIsNotNone(self.view._empty)

    def test_changing_configuration_rebuilds_it(self):
        first = self.view._empty
        self.view.set_configured(False)
        self.assertIsNotNone(self.view._empty)
        self.assertIsNot(self.view._empty, first)

    def test_the_project_line_changes_in_place_without_replaying_the_compass(self):
        self.view.set_configured(True)
        card = self.view._empty
        self.view.set_project_line("roads.qgz · 3 layers · EPSG:3857")
        self.assertIs(self.view._empty, card)
        self.assertEqual(card.project.label.text(), "roads.qgz · 3 layers · EPSG:3857")
        self.assertFalse(card.project.isHidden())
        self.view.set_project_line("")
        self.assertTrue(card.project.isHidden())


class ThinkingFeedTest(unittest.TestCase):
    def setUp(self):
        self.view = ConversationView()

    def test_the_first_delta_opens_a_block(self):
        self.view.append_thinking("hmm")
        self.assertIsNotNone(self.view._thinking)

    def test_later_deltas_grow_the_same_block(self):
        self.view.append_thinking("hm")
        block = self.view._thinking
        self.view.append_thinking("m")
        self.assertIs(self.view._thinking, block)
        self.assertEqual(block._text, "hmm")

    def test_the_answer_folds_the_block_instead_of_dropping_it(self):
        self.view.append_thinking("hmm")
        block = self.view._thinking
        self.view.append_draft("the answer")
        self.assertIsNone(self.view._thinking)
        self.assertTrue(block._finished)

    def test_a_tool_call_folds_the_block(self):
        self.view.append_thinking("hmm")
        block = self.view._thinking
        self.view.add_activity_step("Reading the project.")
        self.assertTrue(block._finished)

    def test_a_new_turn_gets_its_own_block(self):
        self.view.append_thinking("first turn")
        first = self.view._thinking
        self.view.add_activity_step("Reading the project.")
        self.view.append_thinking("second turn")
        self.assertIsNot(self.view._thinking, first)

    def test_clearing_forgets_the_block(self):
        self.view.append_thinking("hmm")
        self.view.clear()
        self.assertIsNone(self.view._thinking)


class CompactFeedTest(unittest.TestCase):
    def setUp(self):
        self.view = ConversationView()

    def test_thinking_no_longer_breaks_the_activity_group(self):
        self.view.add_activity_step("read the project")
        group = self.view._activity
        self.view.append_thinking("hmm")
        self.view.add_activity_step("download the cafes")
        self.assertIs(self.view._activity, group)

    def test_a_whole_turn_chain_is_one_group(self):
        self.view.append_thinking("plan")
        group = self.view._activity
        for step in ("one", "two", "three"):
            self.view.add_activity_step(step)
            self.view.append_thinking("next")
        self.assertIs(self.view._activity, group)

    def test_thinking_starts_inside_an_open_group(self):
        self.view.append_thinking("hmm")
        self.assertTrue(self.view._activity.expanded)

    def test_calls_show_open_while_the_agent_works(self):
        self.view.add_activity_step("Reading the project.")
        self.assertTrue(self.view._activity.expanded)
        self.assertFalse(self.view._activity._rows_holder.isHidden())

    def test_the_answer_folds_the_group_to_its_header(self):
        self.view.add_activity_step("Reading the project.")
        self.view.add_activity_step("Rendering the map.")
        group = self.view._activity
        self.view.add_assistant_message("done")
        self.assertFalse(group.expanded)
        self.assertTrue(group._rows_holder.isHidden())
        self.assertIsNone(self.view._activity)

    def test_a_finished_answer_folds_it_too(self):
        self.view.add_activity_step("Reading the project.")
        self.view.add_activity_step("Rendering the map.")
        group = self.view._activity
        self.view.append_draft("the answer")
        self.view.finish_draft("the answer")
        self.assertFalse(group.expanded)

    def test_a_dropped_draft_leaves_the_group_open_for_the_next_step(self):
        self.view.add_activity_step("first")
        group = self.view._activity
        self.view.append_draft("preamble that never lands")
        self.view.add_activity_step("second")
        self.assertIs(self.view._activity, group)

    def test_a_kept_answer_starts_a_new_group_after_it(self):
        self.view.add_activity_step("first")
        group = self.view._activity
        self.view.append_draft("an answer")
        self.view.finish_draft("an answer")
        self.view.add_activity_step("second")
        self.assertIsNot(self.view._activity, group)


class ThinkingBlockTest(unittest.TestCase):
    def test_it_starts_open_so_the_reasoning_is_visible(self):
        self.assertTrue(ThinkingBlock().expanded)

    def test_reasoning_watched_live_reports_how_long_it_took(self):
        with mock.patch("ai_agent.ui.thinking.time.monotonic", side_effect=[100.0, 103.0, 103.0, 103.0]):
            block = ThinkingBlock()
            block.append("one")
            block.append("two")
            block.finish()
        self.assertTrue(block.time.text())

    def test_a_burst_too_short_to_measure_claims_no_duration(self):
        block = ThinkingBlock()
        block.append("one")
        block.append("two")
        block.finish()
        self.assertEqual(block.time.text(), "")

    def test_reasoning_that_arrived_whole_claims_no_duration(self):
        block = ThinkingBlock()
        block.append("the whole monologue at once")
        block.finish()
        self.assertEqual(block.time.text(), "")

    def test_finishing_twice_changes_nothing(self):
        block = ThinkingBlock()
        block.append("a")
        block.append("b")
        block.finish()
        first = block.time.text()
        block.finish()
        self.assertEqual(block.time.text(), first)


class AssistantMessageTest(unittest.TestCase):
    def test_appending_accumulates_without_losing_anything(self):
        message = AssistantMessage("")
        for part in ("# Title", "\n\nbody ", "text"):
            message.append(part)
        self.assertEqual(message._markdown, "# Title\n\nbody text")

    def test_repainting_is_coalesced_rather_than_run_per_delta(self):
        message = AssistantMessage("")
        message.append("a")
        message.append("b")
        message.append("c")
        self.assertEqual(message._repaint.started, 1)

    def test_finalising_renders_at_once_and_stops_the_pending_repaint(self):
        message = AssistantMessage("")
        message.append("draft")
        message.set_markdown("final")
        self.assertEqual(message._markdown, "final")
        self.assertEqual(message._repaint.stopped, 1)

    def test_copy_text_keeps_the_whole_answer(self):
        message = AssistantMessage("**answer**")
        self.assertEqual(message.plain_text(), "**answer**")


if __name__ == "__main__":
    unittest.main()


class ActivityTitleTest(unittest.TestCase):
    def test_every_turn_with_steps_has_the_trace_header(self):
        view = ConversationView()
        view.append_thinking("hmm")
        view.add_activity_step("Reading layer roads")
        self.assertFalse(view._activity._header.isHidden())
        self.assertIn("2", view._activity._header.title.text())

    def test_a_reasoning_only_turn_stays_shown_without_a_header(self):
        view = ConversationView()
        view.append_thinking("hmm")
        group = view._activity
        self.assertTrue(group._header.isHidden())
        view.add_result_message("Three layers.")
        self.assertTrue(group._header.isHidden())
        self.assertFalse(group._rows_holder.isHidden(), "the turn's only reasoning folded out of sight")

    def test_reasoning_deltas_are_painted_in_batches(self):
        block = ThinkingBlock()
        for delta in ("a", "b", "c"):
            block.append(delta)
        self.assertEqual(block._body.text(), "a")
        block._repaint.fire()
        self.assertEqual(block._body.text(), "abc")
        block.append("d")
        block.finish()
        self.assertEqual(block._body.text(), "abcd")

    def test_while_working_the_header_counts_the_step_then_names_the_trace(self):
        view = ConversationView()
        entry = view.add_activity_step("Reading the project.")
        self.assertEqual(view._activity._header.title.text(), "Working · step 1")
        view.add_activity_step("Rendering the map.")
        self.assertEqual(view._activity._header.title.text(), "Working · step 2")
        group = view._activity
        view.mark_activity_step(entry, True)
        view.add_assistant_message("done")
        self.assertEqual(group._header.title.text(), "Activity · 2 steps")

    def test_a_finished_group_shows_how_long_it_took(self):
        view = ConversationView()
        view.add_activity_step("Reading the project.")
        group_step = view.add_activity_step("Rendering the map.")
        group = view._activity
        with mock.patch("ai_agent.ui.activity.time.monotonic", return_value=group._started + 9.4):
            view.mark_activity_step(group_step, True)
        view.add_assistant_message("done")
        self.assertIn("9.4", group._header.time.text())

    def test_a_row_shows_what_the_call_found_and_its_time(self):
        view = ConversationView()
        summary = CallSummary.marking("Geocoding 'Rotterdam'.", {"query": "Rotterdam"})
        summary.skill = "web"
        entry = view.add_activity_step(summary)
        row = view._entries[entry]
        with mock.patch("ai_agent.ui.activity.time.monotonic", return_value=row.started + 0.8):
            view.mark_activity_step(entry, True, "Rotterdam, Zuid-Holland, Nederland")
        self.assertEqual(row.note.text(), "Rotterdam, Zuid-Holland, Nederland")
        self.assertFalse(row.note.isHidden())
        self.assertIn("0.8", row.meta.text())
        failed = view.add_activity_step("Reading layer 'nope'.")
        view.mark_activity_step(failed, False, "The step did not run.")
        self.assertEqual(view._entries[failed].note.text(), "The step did not run.")
        self.assertFalse(view._entries[failed].note.isHidden())

    def test_a_running_step_pulses_and_settles_into_its_glyph(self):
        from ai_agent.ui.activity import PENDING, PulseRing

        view = ConversationView()
        entry_id = view.add_activity_step("Reading the project.")
        row = view._entries[entry_id]
        self.assertEqual(row.state, PENDING)
        self.assertIsInstance(row.glyph, PulseRing)
        view.mark_activity_step(entry_id, True)
        self.assertNotIsInstance(row.glyph, PulseRing)

    def test_only_failures_are_marked_and_they_are_counted(self):
        view = ConversationView()
        for text in ("Reading the project.", "Labels", "Buffer"):
            view.mark_activity_step(view.add_activity_step(text), text == "Reading the project.")
        self.assertIn("2", view._activity._header.status.text())
        self.assertFalse(view._activity._header.status.isHidden())

    def test_a_rejected_attempt_is_not_counted_as_a_failure(self):
        view = ConversationView()
        view.add_rejected_step("Bad arguments")
        self.assertTrue(view._activity._header.status.isHidden())

    def test_steps_are_escaped_not_rendered(self):
        from qgis.PyQt.QtWidgets import QWidget

        from ai_agent.ui.activity import StepRow

        row = StepRow("<b>visible literally</b><!-- hidden -->", QWidget().palette())
        self.assertIn("&lt;b&gt;visible literally&lt;/b&gt;", row._label.text())

    def test_the_rows_are_joined_by_the_timeline(self):
        view = ConversationView()
        view.append_thinking("hmm")
        for text in ("one", "two", "three"):
            view.add_activity_step(text)
        items = view._activity.items
        self.assertEqual(len(items), 4)
        self.assertEqual([item.connected for item in items], [True, True, True, False])


class FailedPlanCardTest(unittest.TestCase):
    def test_a_failed_apply_still_settles_the_card(self):
        from ai_agent.ui.plan import PlanCard

        card = PlanCard(["step"])
        card.mark_failed()
        self.assertFalse(card._buttons.isVisible())

    def test_plan_steps_are_rendered_as_plain_text(self):
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QLabel, QWidget

        from ai_agent.ui import plan as plan_module

        labels = []

        class RecordingLabel(QLabel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                labels.append(self)

        with mock.patch.object(plan_module, "QLabel", RecordingLabel):
            step = plan_module.PlanStep(1, "<b>weather</b><!-- hidden -->", QWidget().palette())
        self.assertEqual(step.label.textFormat(), Qt.TextFormat.PlainText)

    def test_a_failed_step_shows_its_mark_and_reason_and_a_done_one_only_its_mark(self):
        from ai_agent.ui import plan as plan_module

        card = plan_module.PlanCard(["Downloading roads.", "Styling roads."])
        card.mark_step(0, "running")
        self.assertEqual(card._steps[0].mark.text(), plan_module.RUNNING_MARK)
        card.mark_step(0, "failed", "The service did not answer in time.")
        self.assertEqual(card._steps[0].mark.text(), plan_module.FAILED_MARK)
        self.assertEqual(card._steps[0].reason.text(), "The service did not answer in time.")
        self.assertFalse(card._steps[0].reason.isHidden())
        card.mark_step(1, "done", "ignored")
        self.assertEqual(card._steps[1].mark.text(), plan_module.APPLIED_MARK)
        self.assertTrue(card._steps[1].reason.isHidden())
        card.mark_step(5, "done")


class TraceHeaderTest(unittest.TestCase):
    def test_a_click_anywhere_on_the_line_folds_and_unfolds(self):
        from types import SimpleNamespace

        from qgis.PyQt.QtCore import Qt

        from ai_agent.ui.activity import TraceHeader

        line = TraceHeader(ConversationView().palette())
        seen: list[bool] = []
        line.toggled.connect(seen.append)
        click = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton)
        line.mouseReleaseEvent(click)
        line.mouseReleaseEvent(click)
        self.assertEqual(seen, [True, False])
        self.assertFalse(line.expanded)


class DurationTest(unittest.TestCase):
    def test_seconds_minutes_and_whole_seconds_never_rounded_up(self):
        from ai_agent.ui.durations import format_seconds

        self.assertEqual(format_seconds(3.44), "3.4 s")
        self.assertEqual(format_seconds(5.9, decimals=0), "5 s")
        self.assertEqual(format_seconds(125.0), "2 min 5 s")


class StatusLineTest(unittest.TestCase):
    """The line under the feed says how the run stands once it stops working."""

    def setUp(self):
        from ai_agent.ui import compass, progress

        self.compass = compass
        self.progress = progress
        self.view = ConversationView()
        self.line = self.view.progress

    def test_working_shows_the_searching_compass(self):
        self.line.start()
        self.assertFalse(self.line.isHidden())
        self.assertEqual(self.line.step_text, self.progress.WORKING)
        self.assertEqual(self.line.compass.state, self.compass.SEARCH)

    def test_a_plain_stop_hides_the_line(self):
        self.line.start()
        self.line.stop()
        self.assertTrue(self.line.isHidden())

    def test_a_question_keeps_the_line_waiting_after_the_run_stops(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_WAITING)
        self.line.stop()
        self.assertFalse(self.line.isHidden())
        self.assertEqual(self.line.step_text, self.progress.WAITING)
        self.assertEqual(self.line.compass.state, self.compass.ASK)

    def test_done_says_how_long_it_took(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_DONE)
        self.assertEqual(self.line.step_text, self.progress.DONE_IN.format("0 s"))
        self.assertEqual(self.line.compass.state, self.compass.DONE)

    def test_a_failure_shakes_the_needle(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_FAILED)
        self.assertEqual(self.line.step_text, self.progress.FAILED)
        self.assertEqual(self.line.compass.state, self.compass.ERROR)

    def test_another_conversation_drops_the_old_outcome_but_not_a_live_run(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_DONE)
        self.view.clear()
        self.assertTrue(self.line.isHidden())
        self.line.start()
        self.view.clear()
        self.assertFalse(self.line.isHidden())
