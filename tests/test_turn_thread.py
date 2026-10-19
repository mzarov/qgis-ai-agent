import unittest
from unittest import mock

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent import turn_thread
from ai_agent.core.agent.turn_thread import TurnThreadOwner


class Thread(QObject):
    finished_turn = pyqtSignal(object)
    error = pyqtSignal(object)
    chunk = pyqtSignal(str)
    thinking = pyqtSignal(str)
    retrying = pyqtSignal(object)
    finished = pyqtSignal()

    made: list["Thread"] = []

    def __init__(self, messages, tool_schemas, overrides):
        super().__init__()
        self.running = False
        self.cancelled = False
        self.finishes_in_time = True
        Thread.made.append(self)

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def cancel(self):
        self.cancelled = True

    def wait(self, timeout):
        return self.finishes_in_time

    def deleteLater(self):
        return None

    def end(self):
        self.running = False
        self.finished.emit()


class TurnThreadOwnerTest(unittest.TestCase):
    def setUp(self):
        Thread.made = []
        patcher = mock.patch.object(turn_thread, "ModelTurnThread", Thread)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(turn_thread._ORPHANS.clear)
        self.owner = TurnThreadOwner()
        self.seen = []

    def start(self, optional=True):
        slots = [lambda value, kind=kind: self.seen.append((kind, value)) for kind in ("turn", "error", "chunk")]
        slots += [lambda value, kind=kind: self.seen.append((kind, value)) for kind in ("thinking", "retry")]
        self.slots = slots if optional else slots[:2]
        self.owner.start([], [], {}, *self.slots)
        return Thread.made[-1]

    def emit_all(self, thread):
        thread.chunk.emit("Hel")
        thread.thinking.emit("hmm")
        thread.retrying.emit("in 4 s")
        thread.finished_turn.emit("turn")
        thread.error.emit("HTTP 500")

    def test_every_callback_given_hears_the_thread(self):
        thread = self.start()
        self.assertTrue(self.owner.is_running)
        self.emit_all(thread)
        self.assertEqual(
            self.seen,
            [("chunk", "Hel"), ("thinking", "hmm"), ("retry", "in 4 s"), ("turn", "turn"), ("error", "HTTP 500")],
        )

    def test_a_callback_not_given_is_not_connected(self):
        thread = self.start(optional=False)
        self.emit_all(thread)
        self.assertEqual(self.seen, [("turn", "turn"), ("error", "HTTP 500")])

    def test_a_released_running_thread_is_kept_until_it_finishes(self):
        thread = self.start()
        self.owner.release()
        self.assertFalse(self.owner.is_running)
        self.assertEqual(self.owner._retired, [thread])
        thread.end()
        self.assertEqual(self.owner._retired, [])

    def test_a_released_thread_that_already_ended_is_not_kept(self):
        thread = self.start()
        thread.running = False
        self.owner.release()
        self.assertEqual(self.owner._retired, [])

    def test_detaching_cancels_the_thread_and_nothing_reaches_the_run_any_more(self):
        thread = self.start()
        self.owner.detach(*self.slots)
        self.assertTrue(thread.cancelled)
        self.assertEqual(self.owner._retired, [thread])
        self.emit_all(thread)
        self.assertEqual(self.seen, [])
        thread.end()
        self.assertEqual(self.owner._retired, [])

    def test_detaching_survives_a_slot_that_is_already_gone(self):
        thread = self.start()
        thread.chunk.disconnect(self.slots[2])
        self.owner.detach(*self.slots)
        self.assertTrue(thread.cancelled)
        thread.finished_turn.emit("late turn")
        self.assertEqual(self.seen, [])

    def test_detaching_with_no_thread_does_nothing(self):
        self.owner.detach(lambda turn: None, lambda error: None)
        self.assertEqual(self.owner._retired, [])

    def test_a_thread_is_retired_once(self):
        thread = self.start()
        self.owner.release()
        self.owner._retire(thread)
        self.assertEqual(self.owner._retired, [thread])

    def test_stop_waits_for_running_threads_and_keeps_one_that_outlives_the_wait(self):
        quick = self.start()
        self.owner.release()
        stuck = self.start()
        stuck.finishes_in_time = False
        self.owner.release()
        ended = self.start()
        ended.running = False
        self.owner.stop()
        self.assertFalse(ended.cancelled, "a thread that already ended needs no cancel")
        self.assertTrue(quick.cancelled and stuck.cancelled)
        self.assertEqual(turn_thread._ORPHANS, [stuck])
        turn_thread._keep_until_finished(stuck)
        self.assertEqual(turn_thread._ORPHANS, [stuck])
        stuck.end()
        self.assertEqual(turn_thread._ORPHANS, [])


if __name__ == "__main__":
    unittest.main()
