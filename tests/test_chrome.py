import unittest
from types import SimpleNamespace

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.ui.composer import Composer
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.layer_chip import LayerChip


class LayerChipTest(unittest.TestCase):
    """The active layer rides into the next request until the user drops it or another layer takes over."""

    def setUp(self):
        self.chip = LayerChip(QWidget().palette())

    def test_the_active_layer_shows_with_what_it_holds(self):
        self.chip.set_layer("districts", "12 features")
        self.assertFalse(self.chip.isHidden())
        self.assertEqual(self.chip.label.text(), "districts · 12 features")
        self.assertEqual(self.chip.active_name, "districts")

    def test_a_drop_lasts_until_another_layer_is_active(self):
        self.chip.set_layer("districts", "12 features")
        self.chip.drop()
        self.assertTrue(self.chip.isHidden())
        self.assertEqual(self.chip.active_name, "")
        self.chip.set_layer("districts", "13 features")
        self.assertTrue(self.chip.isHidden(), "the same layer stays dropped")
        self.chip.set_layer("roads", "")
        self.assertEqual(self.chip.active_name, "roads")
        self.assertEqual(self.chip.label.text(), "roads")

    def test_no_active_layer_hides_the_chip(self):
        self.chip.set_layer("districts", "12 features")
        self.chip.set_layer("", "")
        self.assertTrue(self.chip.isHidden())


class ComposerContextTest(unittest.TestCase):
    def setUp(self):
        self.composer = Composer()

    def test_the_chip_becomes_a_quoted_mention(self):
        self.assertEqual(self.composer.context_mention(), "")
        self.composer.set_active_layer("Main roads", "40 features")
        self.assertEqual(self.composer.context_mention(), '@"Main roads"')
        self.assertFalse(self.composer._chips.isHidden())
        self.composer.layer_chip.drop()
        self.assertEqual(self.composer.context_mention(), "")
        self.assertTrue(self.composer._chips.isHidden(), "an empty chip row takes no room")

    def test_a_chosen_skill_goes_first_and_the_typed_text_stays(self):
        self.composer._edit.setPlainText("colour the rivers")
        self.composer._insert_skill("style")
        self.assertEqual(self.composer._edit.toPlainText(), "/style colour the rivers ")
        self.composer._edit.setPlainText("/sty")
        self.composer._insert_skill("style")
        self.assertEqual(self.composer._edit.toPlainText(), "/style ")

    def test_the_model_is_said_not_offered(self):
        from qgis.PyQt.QtWidgets import QAbstractButton

        from ai_agent.ui import composer_controls

        self.composer.set_model("moonshotai/kimi-k2.5")
        self.assertEqual(self.composer.toolbar.model.text(), "kimi-k2.5")
        self.assertEqual(self.composer.toolbar.model.toolTip(), "moonshotai/kimi-k2.5")
        # A plain label, nothing to click: choosing a model belongs to the settings (the user's call).
        self.assertNotIsInstance(self.composer.toolbar.model, QAbstractButton)
        self.composer.set_model("")
        self.assertEqual(self.composer.toolbar.model.text(), composer_controls.NO_MODEL)

    def test_modes_are_one_word_each(self):
        from ai_agent.ui.composer_parts import MODES

        self.assertEqual([len(choice.title.split()) for choice in MODES], [1, 1, 1])

    def test_the_mode_menu_carries_its_shift_tab_footer(self):
        from ai_agent.ui import composer_controls

        self.assertIn("Shift+Tab", composer_controls.MODE_FOOTER)

    def test_ctrl_n_in_the_box_asks_for_a_new_conversation(self):
        asked = []
        self.composer.new_requested.connect(lambda: asked.append(True))
        event = SimpleNamespace(matches=lambda sequence: True, key=lambda: 0, modifiers=lambda: 0)
        self.composer._edit.keyPressEvent(event)
        self.assertEqual(asked, [True])


class SendButtonTest(unittest.TestCase):
    def test_send_turns_into_stop_while_the_agent_works(self):
        composer = Composer()
        self.assertEqual(composer._send.toolTip(), "Send")
        self.assertFalse(composer._send.isEnabled(), "nothing to send yet")
        composer.set_busy(True)
        self.assertEqual(composer._send.toolTip(), "Stop")
        self.assertTrue(composer._send.isEnabled(), "stop works with an empty box")
        self.assertTrue(composer._send.busy)


class NewConversationButtonTest(unittest.TestCase):
    def test_the_plus_waits_for_a_conversation_to_start_over_from(self):
        from ai_agent.ui.dock_widget import AgentDockWidget

        dock = AgentDockWidget()
        self.assertFalse(dock.toolbar.new_button.isEnabled())
        dock.add_user_message("hello")
        self.assertTrue(dock.toolbar.new_button.isEnabled())
        dock.replay([])
        self.assertFalse(dock.toolbar.new_button.isEnabled())

    def test_the_title_falls_back_to_new_conversation(self):
        from ai_agent.ui import dock_widget
        from ai_agent.ui.dock_widget import AgentDockWidget

        dock = AgentDockWidget()
        dock.set_conversation_title("Districts by population")
        self.assertEqual(dock.toolbar.title.label.text(), "Districts by population")
        dock.set_conversation_title("")
        self.assertEqual(dock.toolbar.title.label.text(), dock_widget.NEW_CONVERSATION_TITLE)


class SavedHintTest(unittest.TestCase):
    def test_the_welcome_says_where_the_previous_conversation_went_until_a_message(self):
        view = ConversationView()
        view.show_saved_hint()
        self.assertFalse(view._empty.saved.isHidden())
        view.set_configured(False)
        self.assertFalse(view._empty.saved.isHidden(), "a rebuilt welcome keeps the line")
        view.add_user_message("hello")
        view.clear()
        self.assertTrue(view._empty.saved.isHidden(), "another conversation has nothing to say about it")


class SessionsPopupTest(unittest.TestCase):
    def test_the_first_row_starts_a_new_conversation(self):
        from ai_agent.ui.sessions_popup import SessionsPopup

        popup = SessionsPopup(QWidget().palette())
        asked = []
        popup.new_requested.connect(lambda: asked.append(True))
        popup.new_row.clicked.emit()
        self.assertEqual(asked, [True])


class NewConversationTransitionTest(unittest.TestCase):
    """The handoff's new conversation: the old feed leaves, then the welcome arrives."""

    def test_the_arrival_runs_on_the_handoff_curve_with_the_saved_line_behind(self):
        from ai_agent.ui import transitions

        self.assertEqual(transitions.arrival(0), 0.0)
        self.assertAlmostEqual(transitions.arrival(transitions.ARRIVE_MS), 1.0, places=3)
        self.assertEqual(transitions.arrival(transitions.LAG_MS, transitions.LAG_MS), 0.0)
        middle = transitions.arrival(transitions.ARRIVE_MS / 2)
        # cubic-bezier(.2,.7,.3,1) is quick at first: half the time is well past half the way.
        self.assertGreater(middle, 0.75)
        self.assertLess(transitions.arrival(200, transitions.LAG_MS), middle)

    def _dock(self):
        from ai_agent.ui.dock_widget import AgentDockWidget

        dock = AgentDockWidget()
        played = []
        dock.conversation.play_new_conversation = played.append
        dock.conversation.snapshot = lambda: "picture of the old feed"
        return dock, played

    def test_a_confirmed_switch_plays_the_transition_with_the_old_feed(self):
        dock, played = self._dock()

        def switch():
            dock.replay([])
            dock.note_conversation_saved()

        dock.new_session_clicked.connect(switch)
        dock.toolbar.new_requested.emit()
        self.assertEqual(played, ["picture of the old feed"])
        self.assertIsNone(dock._leaving)

    def test_a_refused_switch_drops_the_picture(self):
        dock, played = self._dock()
        dock.new_session_clicked.connect(lambda: None)
        dock.toolbar.new_requested.emit()
        dock.note_conversation_saved()
        self.assertEqual(played, [])

    def test_only_a_feed_with_messages_has_anything_to_see_leave(self):
        view = ConversationView()
        self.assertIsNone(view.snapshot())


class EntranceTest(unittest.TestCase):
    """The chat rises in the way a new conversation's welcome does: on the first message and on opening one."""

    def _view(self):
        view = ConversationView()
        played = []
        view.snapshot = lambda with_welcome=False: "picture" if with_welcome else None
        view.play_entrance = played.append
        return view, played

    def test_the_first_message_on_the_welcome_plays_the_entrance_once(self):
        view, played = self._view()
        view.add_user_message("hello")
        view.add_user_message("and more")
        self.assertEqual(played, ["picture"])

    def test_a_replayed_message_does_not(self):
        view, played = self._view()
        view.add_user_message("hello", animate=False)
        self.assertEqual(played, [])

    def test_opening_a_conversation_from_the_history_plays_it_after_the_replay(self):
        from ai_agent.ui.dock_widget import AgentDockWidget

        dock = AgentDockWidget()
        played = []
        dock.conversation.snapshot = lambda with_welcome=False: "old feed"
        dock.conversation.play_entrance = played.append
        dock.session_chosen.connect(lambda identifier: dock.replay([{"role": "user", "content": identifier}]))
        dock._sessions_popup.chosen.emit("past")
        self.assertEqual(played, ["old feed"])
        self.assertIsNone(dock._switching)

    def test_the_open_conversation_is_not_opened_again(self):
        from ai_agent.ui.sessions_popup import Entry, SessionsPopup

        popup = SessionsPopup(QWidget().palette())
        chosen = []
        popup.chosen.connect(chosen.append)
        popup.show_sessions([Entry("open", "Open one", 0.0, True), Entry("past", "Past one", 0.0)], QWidget(), 0.0)
        popup._choose("open")
        popup._choose("past")
        self.assertEqual(chosen, ["past"])


class ReopenedTurnTest(unittest.TestCase):
    """A reopened conversation draws the saved steps, reasoning, choices and plan cards again."""

    def test_the_replay_rebuilds_the_trace_the_choice_and_the_plan(self):
        from ai_agent.ui.activity import ActivityGroup
        from ai_agent.ui.dock_widget import AgentDockWidget
        from ai_agent.ui.plan import PlanCard

        dock = AgentDockWidget()
        trace = {
            "steps": [
                {"kind": "thought", "text": "Let me look.", "seconds": 2.0},
                {"kind": "call", "text": "Using inspect", "parts": [], "skill": "knowledge", "ok": True},
                {
                    "kind": "call",
                    "text": "Reading layer 'roads'",
                    "parts": [["roads", True]],
                    "skill": "inspect",
                    "ok": False,
                    "note": "No such layer",
                    "seconds": 0.4,
                },
            ],
            "seconds": 2.4,
        }
        plan = {"lines": ["Styling 'rivers' blue"], "state": "applied", "at": "14:32", "marks": [["done", ""]]}
        dock.replay(
            [
                {"role": "user", "content": "Which layers?"},
                {"role": "trace", "trace": trace},
                {"role": "assistant", "content": "Which field?"},
                {"role": "user", "content": "pop2020", "chosen": True},
                {"role": "plan", "plan": plan},
            ]
        )
        entries = list(dock.conversation._entries.values())
        groups = list({id(entry): entry for entry in entries if isinstance(entry, ActivityGroup)}.values())
        self.assertEqual(len(groups), 2, "the saved trace and the choice each draw a group")
        rebuilt = groups[0]
        self.assertEqual(len(rebuilt.items), 3)
        self.assertFalse(rebuilt.expanded, "a reopened turn rests folded")
        self.assertEqual(rebuilt._failures, 1)
        self.assertEqual(rebuilt._header.time.text(), "2.4 s")
        card = next(entry for entry in entries if isinstance(entry, PlanCard))
        self.assertIn("14:32", card._status_text.text())
        self.assertTrue(card._undo.isHidden(), "the snapshot died with that session")


if __name__ == "__main__":
    unittest.main()
