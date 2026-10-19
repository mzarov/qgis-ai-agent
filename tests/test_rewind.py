import shutil
import tempfile
import unittest
from unittest import mock

from ai_agent.core.orchestrator import rewind
from ai_agent.core.orchestrator.notices import REWIND_BOTH, REWIND_CONVERSATION, REWIND_PROJECT
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.session import MAX_MESSAGES, Session
from ai_agent.core.state.store import SessionStore
from ai_agent.ui.dock_widget import AgentDockWidget
from ai_agent.ui.messages import UserMessage
from tests.test_orchestrator import Agent, Dock, Iface


class TruncateTest(unittest.TestCase):
    def test_a_summary_of_forgotten_messages_goes_with_them(self):
        session = Session.create("/p.qgz")
        for text in ("a", "b", "c", "d"):
            session.add("user", text)
        session.compact("summary", keep=1, upto=4)
        session.context_tokens = 900
        session.truncate(1)
        self.assertEqual([m["content"] for m in session.messages], ["a"])
        self.assertEqual((session.summary, session.summary_index, session.context_tokens), ("", 0, 0))


class RewindDock(Dock):
    def __init__(self, choice):
        super().__init__()
        self.choice = choice
        self.offered = None
        self.restored = None
        self.marks = []
        self.errors = []
        self.while_asked = lambda: None

    def choose_rewind(self, project_available):
        self.offered = project_available
        self.while_asked()
        return self.choice

    def add_error_message(self, text):
        self.errors.append(text)

    def restore_prompt(self, text):
        self.restored = text

    def mark_rewind_point(self, entry, message):
        self.marks.append(message)


class RewindTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.snapshots = []
        self.live = set()
        patches = [
            mock.patch.object(
                rewind, "last_snapshot", side_effect=lambda: self.snapshots[-1] if self.snapshots else ""
            ),
            mock.patch.object(rewind, "snapshot_exists", side_effect=lambda path: path in self.live),
            mock.patch.object(rewind, "restore_snapshot", side_effect=self._restore),
            mock.patch.object(rewind, "drop_snapshot", side_effect=self.live.discard),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.restored = []

    def _restore(self, path):
        self.restored.append(path)
        self.live.discard(path)
        return {"restored_from": path}

    def orchestrator(self, choice):
        dock = RewindDock(choice)
        orchestrator = CoreOrchestrator(Iface(), dock)
        orchestrator.conversation = ConversationState(store=SessionStore(self.root))
        orchestrator.agent = Agent()
        return orchestrator, dock

    def _turn(self, orchestrator, text, snapshot=""):
        orchestrator.on_prompt(text)
        if snapshot:
            orchestrator._note_apply_start()
            self.snapshots.append(snapshot)
            self.live.add(snapshot)
            orchestrator._record_checkpoint()
        orchestrator.on_finished(f"done: {text}")

    def test_both_restores_the_snapshot_before_the_message_and_drops_the_later_ones(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        self._turn(orchestrator, "second", "s2")
        self._turn(orchestrator, "third", "s3")
        self.assertEqual(dock.marks, [0, 2, 4])
        orchestrator.on_rewind(2)
        self.assertTrue(dock.offered)
        self.assertEqual(self.restored, ["s2"])
        self.assertEqual(self.live, {"s1"})
        self.assertEqual([m["content"] for m in orchestrator.conversation.messages], ["first", "done: first"])
        self.assertEqual(dock.restored, "second")
        self.assertIsNone(orchestrator.checkpoint_for(2))
        self.assertEqual(orchestrator.checkpoint_for(0).snapshot, "s1")

    def test_a_message_with_no_snapshot_after_it_offers_the_conversation_only(self):
        orchestrator, dock = self.orchestrator(REWIND_CONVERSATION)
        self._turn(orchestrator, "first", "s1")
        self._turn(orchestrator, "question only")
        orchestrator.on_rewind(2)
        self.assertFalse(dock.offered)
        self.assertEqual(self.restored, [])
        self.assertEqual(len(orchestrator.conversation.messages), 2)

    def test_project_only_keeps_the_conversation_and_a_cancel_changes_nothing(self):
        orchestrator, dock = self.orchestrator(REWIND_PROJECT)
        self._turn(orchestrator, "first", "s1")
        orchestrator.on_rewind(0)
        self.assertEqual(self.restored, ["s1"])
        self.assertEqual(len(orchestrator.conversation.messages), 2)
        dock.choice = None
        self._turn(orchestrator, "second", "s2")
        orchestrator.on_rewind(2)
        self.assertEqual(self.restored, ["s1"])
        self.assertEqual(len(orchestrator.conversation.messages), 4)

    def test_rewind_points_and_checkpoints_outlive_the_head_trimmed_past_the_cap(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        turns = MAX_MESSAGES // 2 + 10
        early, late = 15, turns - 1
        for number in range(turns):
            self._turn(orchestrator, f"request {number}", f"s{number}" if number in (early, late) else "")
        conversation = orchestrator.conversation
        self.assertEqual(len(conversation.messages), MAX_MESSAGES, "the cap dropped the head")
        for checkpoint in orchestrator._checkpoints:
            tagged = conversation.message_at(checkpoint.message)
            self.assertEqual(tagged["content"], f"request {checkpoint.snapshot[1:]}")

        orchestrator.on_rewind(dock.marks[late])
        self.assertEqual((self.restored, dock.restored), ([f"s{late}"], f"request {late}"))
        self.assertEqual(conversation.messages[-1]["content"], f"done: request {late - 1}")

        orchestrator.on_rewind(dock.marks[early])
        self.assertEqual((self.restored, dock.restored), ([f"s{late}", f"s{early}"], f"request {early}"))
        self.assertEqual(conversation.messages[-1]["content"], f"done: request {early - 1}")

    def test_nothing_rewinds_while_a_run_is_going(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        orchestrator.agent.is_running = True
        orchestrator.on_rewind(0)
        self.assertIsNone(dock.offered)
        self.assertEqual(self.restored, [])

    def test_a_failed_restore_says_why_and_leaves_the_conversation_and_snapshots(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        self._turn(orchestrator, "second", "s2")
        with mock.patch.object(rewind, "restore_snapshot", side_effect=ValueError("Commit or roll back roads")):
            orchestrator.on_rewind(0)
        self.assertEqual(dock.errors, ["Could not restore the project: Commit or roll back roads"])
        self.assertEqual(len(orchestrator.conversation.messages), 4)
        self.assertIsNone(dock.restored)
        self.assertEqual(self.live, {"s1", "s2"})
        self.assertEqual(orchestrator.checkpoint_for(0).snapshot, "s1")
        self.assertFalse(orchestrator._restoring_snapshot)

    def test_a_snapshot_gone_while_the_choice_was_open_rewinds_the_conversation_only(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        dock.while_asked = lambda: self.live.discard("s1")
        orchestrator.on_rewind(0)
        self.assertTrue(dock.offered)
        self.assertEqual(self.restored, [])
        self.assertEqual(orchestrator.conversation.messages, [])
        self.assertEqual(dock.restored, "first")
        self.assertNotIn(rewind.REWOUND_PROJECT + " " + rewind.DATA_EDITS_NOTE, dock.system)

    def test_only_a_users_message_offers_a_rewind(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        orchestrator.on_rewind(1)
        orchestrator.on_rewind(99)
        self.assertIsNone(dock.offered)
        self.assertEqual(len(orchestrator.conversation.messages), 2)

    def test_temporary_layers_that_came_back_empty_are_named(self):
        orchestrator, dock = self.orchestrator(REWIND_PROJECT)
        self._turn(orchestrator, "first", "s1")
        with mock.patch.object(rewind, "restore_snapshot", return_value={"empty_scratch_layers": ["buffer", "zones"]}):
            orchestrator.on_rewind(0)
        note = dock.system[-1]
        self.assertTrue(note.startswith(rewind.REWOUND_PROJECT), note)
        self.assertIn(rewind.DATA_EDITS_NOTE, note)
        self.assertIn("buffer, zones", note)

    def test_an_apply_before_any_message_leaves_no_rewind_point(self):
        orchestrator, _dock = self.orchestrator(REWIND_BOTH)
        orchestrator._note_apply_start()
        self.snapshots.append("s0")
        self.live.add("s0")
        orchestrator._record_checkpoint()
        self.assertEqual(orchestrator._checkpoints, [])


class ReplayPlaceTest(unittest.TestCase):
    def test_a_reopened_long_conversation_offers_each_bubble_its_own_message(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        state = ConversationState(store=SessionStore(root))
        for number in range(MAX_MESSAGES // 2 + 10):
            state.add("user", f"request {number}")
            state.add("assistant", f"done: request {number}")
        dock = AgentDockWidget()
        dock.replay(state.replayable())

        bubbles = [entry for entry in dock.conversation._entries.values() if isinstance(entry, UserMessage)]
        self.assertEqual(len(bubbles), MAX_MESSAGES // 2)
        for bubble in bubbles:
            self.assertEqual(state.message_at(bubble.message)["content"], bubble.plain_text())


class BubbleTest(unittest.TestCase):
    def test_only_a_placed_message_asks_to_rewind(self):
        bubble = UserMessage("hello")
        asked = []
        bubble.rewind_requested.connect(asked.append)
        bubble._ask_rewind()
        bubble.set_rewind_point(4)
        bubble._ask_rewind()
        self.assertEqual(asked, [4])


if __name__ == "__main__":
    unittest.main()
