import shutil
import tempfile
import unittest
from unittest import mock

from ai_agent.core.orchestrator import rewind
from ai_agent.core.orchestrator.notices import REWIND_BOTH, REWIND_CONVERSATION, REWIND_PROJECT
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.session import Session
from ai_agent.core.state.store import SessionStore
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

    def choose_rewind(self, project_available):
        self.offered = project_available
        return self.choice

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

    def test_nothing_rewinds_while_a_run_is_going(self):
        orchestrator, dock = self.orchestrator(REWIND_BOTH)
        self._turn(orchestrator, "first", "s1")
        orchestrator.agent.is_running = True
        orchestrator.on_rewind(0)
        self.assertIsNone(dock.offered)
        self.assertEqual(self.restored, [])


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
