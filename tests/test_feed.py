import unittest

from qgis_ai_agent.ui.conversation import ConversationView
from qgis_ai_agent.ui.messages import AssistantMessage
from qgis_ai_agent.ui.thinking import ThinkingBlock


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


class WelcomeFeedTest(unittest.TestCase):
    def setUp(self):
        self.view = ConversationView()

    def test_an_empty_feed_shows_the_welcome_card(self):
        self.assertIsNotNone(self.view._empty)

    def test_the_first_message_replaces_it(self):
        self.view.add_user_message("hello")
        self.assertIsNone(self.view._empty)

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
        self.assertTrue(self.view._activity._toggle.isChecked())

    def test_the_answer_folds_the_whole_group(self):
        self.view.append_thinking("hmm")
        group = self.view._activity
        self.view.add_assistant_message("done")
        self.assertFalse(group._toggle.isChecked())
        self.assertIsNone(self.view._activity)

    def test_a_streamed_answer_folds_it_too(self):
        self.view.append_thinking("hmm")
        group = self.view._activity
        self.view.append_draft("the answer")
        self.assertFalse(group._toggle.isChecked())


class ThinkingBlockTest(unittest.TestCase):
    def test_it_starts_open_so_the_reasoning_is_visible(self):
        self.assertTrue(ThinkingBlock()._toggle.isChecked())

    def test_reasoning_watched_live_reports_how_long_it_took(self):
        block = ThinkingBlock()
        block.append("one")
        block.append("two")
        block.finish()
        self.assertTrue(block._elapsed.text())

    def test_reasoning_that_arrived_whole_claims_no_duration(self):
        block = ThinkingBlock()
        block.append("the whole monologue at once")
        block.finish()
        self.assertEqual(block._elapsed.text(), "")

    def test_finishing_twice_changes_nothing(self):
        block = ThinkingBlock()
        block.append("a")
        block.append("b")
        block.finish()
        first = block._elapsed.text()
        block.finish()
        self.assertEqual(block._elapsed.text(), first)


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


if __name__ == "__main__":
    unittest.main()


class ActivityTitleTest(unittest.TestCase):
    def test_a_thinking_only_group_is_not_zero_actions(self):
        view = ConversationView()
        view.append_thinking("hmm")
        title = view._activity._title.text()
        self.assertNotIn("0", title)

    def test_a_group_with_actions_counts_them(self):
        view = ConversationView()
        view.add_activity_step("Reading the project.")
        self.assertIn("1", view._activity._title.text())


class FailedPlanCardTest(unittest.TestCase):
    def test_a_failed_apply_still_settles_the_card(self):
        from qgis_ai_agent.ui.plan import PlanCard

        card = PlanCard(["step"])
        card.mark_failed()
        self.assertFalse(card._buttons.isVisible())
