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
        self.assertIn("self.toolbar.new_requested.connect(self._start_new)", DOCK_SOURCE)
        self.assertIn("self.new_session_clicked.emit()", DOCK_SOURCE)
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

    def test_every_node_says_where_its_drawing_sits_for_the_timeline(self):
        from ai_agent.ui import activity

        view = ConversationView()
        view.append_thinking("hmm")
        view.add_activity_step("one")
        self.assertEqual(len(view._activity.items), 2)
        # The group stops its hairline LINE_GAP short of each drawing, whatever the glyph's size.
        marks = [view._activity._header.chevron.mark, activity.ThinkingDots.mark, activity.PulseRing.mark]
        for top, bottom in [*marks, activity.ICON_MARK]:
            self.assertTrue(0 <= top < bottom <= activity.GLYPH_BOX)


class FailureCardTest(unittest.TestCase):
    def test_a_card_without_retry_offers_it_later_and_names_the_servers_words(self):
        from ai_agent.ui.failure_card import FailureCard

        card = FailureCard(
            "Not found", "Check the address.", "The API returned 404: Not Found", "not_found", True, False
        )
        self.assertTrue(card.retry.isHidden())
        self.assertIn("404", card.technical.text())
        card.offer_retry()
        self.assertFalse(card.retry.isHidden())
        card.retire()
        self.assertTrue(card.retry.isHidden())

    def test_retrying_takes_the_failed_cards_out_of_the_feed(self):
        view = ConversationView()
        view.add_user_message("Which layers?")
        view.add_run_failure("No connection", "The server does not answer.", "refused", "connection", True, True)
        self.assertEqual(len(view._failures), 1)
        view.drop_failures()
        self.assertEqual(view._failures, [])
        self.assertFalse(any(type(entry).__name__ == "FailureCard" for entry in view._entries.values()))

    def test_a_reopened_failure_shows_what_happened_without_buttons(self):
        view = ConversationView()
        view.add_recorded_failure(
            {"title": "No connection", "detail": "The server does not answer.", "kind": "connection"}
        )
        cards = [entry for entry in view._entries.values() if type(entry).__name__ == "FailureCard"]
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0].retry.isHidden())
        self.assertTrue(cards[0].settings.isHidden())
        self.assertEqual(view._failures, [], "a card from the past would take Retry after Settings")

    def test_a_new_request_retires_retry_but_keeps_the_card(self):
        view = ConversationView()
        view.add_run_failure("No connection", "The server does not answer.", "refused", "connection", True, True)
        card = view._failures[0]
        view.add_user_message("Something else")
        self.assertTrue(card.retry.isHidden())
        view.offer_retry()
        self.assertTrue(card.retry.isHidden(), "a retired card came back to life")


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

    def test_a_cancelled_plan_is_offered_back_and_restored_to_apply_and_cancel(self):
        from ai_agent.ui import plan as plan_module

        card = plan_module.PlanCard(["Colouring districts."], layer="Districts")
        self.assertEqual(card.layer.text(), plan_module.LAYER.format("Districts"))
        card.mark_cancelled(restorable=True)
        self.assertFalse(card._restore.isHidden())
        self.assertTrue(card._buttons.isHidden())
        card.restore()
        self.assertFalse(card._buttons.isHidden())
        self.assertTrue(card._status.isHidden())
        self.assertEqual(card._mark.text(), plan_module.PENDING_MARK)
        card.mark_cancelled()
        self.assertTrue(card._restore.isHidden(), "a plan the conversation moved past is not offered back")

    def test_a_long_step_shows_how_far_it_is_until_it_ends(self):
        from ai_agent.ui import plan as plan_module

        card = plan_module.PlanCard(["Buffering roads."])
        card.mark_step(0, "running")
        self.assertTrue(card._buttons.isHidden(), "Apply stays pressable while the plan applies")
        card.mark_progress(0, 64.4)
        step = card._steps[0]
        self.assertEqual(step.mark.text(), "64 %")
        self.assertFalse(step.bar.isHidden())
        self.assertAlmostEqual(step.bar.fraction, 0.644)
        card.mark_step(0, "done")
        self.assertTrue(step.bar.isHidden())
        self.assertEqual(step.mark.text(), plan_module.APPLIED_MARK)

    def test_a_download_of_unknown_size_runs_its_bar_and_counts_its_bytes(self):
        from ai_agent.ui import plan as plan_module
        from ai_agent.ui import sizes

        card = plan_module.PlanCard(["Downloading cafes."])
        card.mark_step(0, "running")
        card.mark_progress(0, -1.0, 0)
        step = card._steps[0]
        self.assertTrue(step.bar.running)
        self.assertEqual(step.mark.text(), plan_module.RUNNING_MARK)
        locale = mock.Mock(toString=lambda value, *_format: f"{value:.1f}")
        with mock.patch.object(sizes, "QLocale", return_value=locale):
            card.mark_progress(0, -1.0, 3 * 1024 * 1024)
        self.assertEqual(step.mark.text(), "3.0 MB")
        card.mark_progress(0, 50.0, 3 * 1024 * 1024)
        self.assertFalse(step.bar.running)
        self.assertEqual(step.mark.text(), "50 %")

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


class LegendCardTest(unittest.TestCase):
    RANGES = {
        "type": "legend",
        "title": "districts",
        "kind": "ranges",
        "items": [{"color": "#c6dbef", "label": "20000.0000 - 35000.0000", "low": 20000.0, "high": 35000.0}] * 5,
        "more": 0,
    }

    def test_ordered_classes_are_one_strip_with_compact_bounds(self):
        from ai_agent.ui.legend import LegendCard, item_label

        card = LegendCard(self.RANGES)
        self.assertTrue(card.as_strip)
        self.assertEqual(item_label(self.RANGES["items"][0]), "20k–35k")
        self.assertEqual(card.plain_text(), "districts")

    def test_categories_and_long_ramps_are_rows_with_the_rest_counted(self):
        from ai_agent.ui.legend import LegendCard, item_label

        categories = {**self.RANGES, "kind": "categories", "items": [{"color": "#1b9e77", "label": "Forest"}]}
        self.assertFalse(LegendCard(categories).as_strip)
        self.assertEqual(item_label(categories["items"][0]), "Forest")
        long_ramp = {**self.RANGES, "items": self.RANGES["items"] * 2, "more": 3}
        self.assertFalse(LegendCard(long_ramp).as_strip)


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
        self.assertEqual(self.line._step.text(), self.progress.WORKING)
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
        self.assertEqual(self.line._step.text(), self.progress.WAITING)
        self.assertEqual(self.line.compass.state, self.compass.ASK)

    def test_done_says_how_long_it_took(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_DONE)
        self.assertEqual(self.line._step.text(), self.progress.DONE_IN.format("0 s"))
        self.assertEqual(self.line.compass.state, self.compass.DONE)

    def test_a_failure_shakes_the_needle(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_FAILED)
        self.assertEqual(self.line._step.text(), self.progress.FAILED)
        self.assertEqual(self.line.compass.state, self.compass.ERROR)

    def test_a_retry_counts_down_and_then_says_it_is_retrying(self):
        clock = [100.0]
        with mock.patch.object(self.progress.time, "monotonic", lambda: clock[0]):
            self.line.start()
            self.line.show_retry(14.0, 2, 5, True)
            self.assertEqual(self.line._step.text(), self.progress.RETRY_BUSY.format("14 s", 2, 5))
            clock[0] += 4.5
            self.line._tick()
            self.assertEqual(self.line._step.text(), self.progress.RETRY_BUSY.format("10 s", 2, 5))
            clock[0] += 10.0
            self.line._tick()
            self.assertEqual(self.line._step.text(), self.progress.RETRYING.format(2, 5))

    def test_a_failed_request_is_not_called_a_busy_model(self):
        self.line.start()
        self.line.show_retry(4.0, 3, 3, False)
        self.assertEqual(self.line._step.text(), self.progress.RETRY_FAILED.format("4 s", 3, 3))

    def test_whatever_reaches_the_feed_ends_the_retry_note(self):
        for arrive in (
            lambda: self.view.add_activity_step("Reading the project."),
            lambda: self.view.append_thinking("Hm."),
            lambda: self.view.append_draft("Three"),
            lambda: self.view.add_system_message("Interjected."),
        ):
            self.view.clear()
            self.line.start()
            self.line.show_retry(14.0, 2, 5, True)
            arrive()
            self.assertEqual(self.line._step.text(), self.progress.WORKING)
            self.line._tick()
            self.assertEqual(self.line._step.text(), self.progress.WORKING)

    def test_a_late_retry_does_not_overwrite_an_outcome(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_FAILED)
        self.line.show_retry(14.0, 2, 5, True)
        self.assertEqual(self.line._step.text(), self.progress.FAILED)

    def test_another_conversation_drops_the_old_outcome_but_not_a_live_run(self):
        self.line.start()
        self.line.show_outcome(self.progress.STATUS_DONE)
        self.view.clear()
        self.assertTrue(self.line.isHidden())
        self.line.start()
        self.view.clear()
        self.assertFalse(self.line.isHidden())
