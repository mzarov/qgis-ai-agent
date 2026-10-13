"""A step that works off the main thread: the batch waits for it without blocking, then goes on."""

import unittest
from unittest import mock

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent import apply_run as apply_run_module
from ai_agent.core.agent import batch_apply as batch_apply_module
from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall


class FakeWork(QObject):
    progressed = pyqtSignal(float)
    counted = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class BackgroundExecutor:
    """run_processing works in the background; every other call runs on the main thread."""

    def __init__(self):
        self.ran = []
        self.works = []
        self._waiting = []

    def start(self, call, done):
        if call.name != "run_processing":
            return None
        work = FakeWork()
        self.works.append(work)
        self._waiting.append((call, done))
        return work

    def run(self, call):
        self.ran.append(call.name)
        return ToolResult(call=call, payload={"ok": True})

    def finish(self, ok=True):
        call, done = self._waiting.pop(0)
        self.ran.append(call.name)
        done(ToolResult(call=call, payload={"done": True}) if ok else ToolResult.failure(call, "Stopped."))


def calls(*names):
    return [ToolCall(id=f"call-{index}", name=name, arguments={}) for index, name in enumerate(names)]


class ApplyRunTest(unittest.TestCase):
    def setUp(self):
        self.executor = BackgroundExecutor()
        self.batch = WriteBatch(self.executor)
        self.batch._calls = calls("set_opacity", "run_processing", "set_symbol")
        self.finished = []
        self.progress = []
        identity = mock.patch.object(apply_run_module, "project_identity", return_value="project")
        identity.start()
        self.addCleanup(identity.stop)

    def apply(self):
        return self.batch.apply(
            lambda call: None,
            lambda call, result: None,
            "project",
            self.finished.append,
            lambda percent, done: self.progress.append((percent, done)),
        )

    def test_the_batch_waits_for_a_background_step_and_then_goes_on(self):
        self.assertIsNone(self.apply(), "a background step cannot have ended before apply returns")
        self.assertEqual(self.executor.ran, ["set_opacity"])
        self.assertTrue(self.batch.is_applying)
        self.assertEqual(self.batch.executing_tool, "run_processing")
        self.assertEqual(self.progress, [(-1.0, 0)], "the step shows it works before it says how far")
        self.executor.works[0].counted.emit(2048)
        self.executor.works[0].progressed.emit(40.0)
        self.assertEqual(self.progress[1:], [(-1.0, 2048), (40.0, 2048)])
        self.executor.finish()
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing", "set_symbol"])
        self.assertEqual([result.ok for result in self.finished[0]], [True, True, True])
        self.assertFalse(self.batch.is_applying)

    def test_a_batch_without_background_steps_ends_before_apply_returns(self):
        self.batch._calls = calls("set_opacity", "set_symbol")
        results = self.apply()
        self.assertEqual([result.ok for result in results], [True, True])
        self.assertEqual(self.finished, [results])

    def test_stopping_cancels_the_background_step_and_the_steps_after_it(self):
        self.apply()
        self.batch.clear()
        self.assertTrue(self.executor.works[0].cancelled)
        self.executor.finish(ok=False)
        oks = [result.ok for result in self.finished[0]]
        self.assertEqual(oks, [True, False, False])
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing"])
        self.assertFalse(self.batch.is_applying)

    def test_a_detached_run_reports_to_nobody(self):
        self.apply()
        self.batch.detach()
        self.assertTrue(self.executor.works[0].cancelled)
        self.assertFalse(self.batch.is_applying)
        self.executor.finish()
        self.assertEqual(self.finished, [])
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing"])


class LoopBackgroundTest(unittest.TestCase):
    def test_the_loop_reports_progress_and_applies_once_the_step_ends(self):
        loop = AgentLoop()
        executor = BackgroundExecutor()
        loop._batch._executor = executor
        loop._batch._calls = calls("run_processing")
        progress, applied, busy = [], [], []
        loop.tool_progressed.connect(lambda percent, done: progress.append(percent))
        loop.applied.connect(applied.append)
        loop.busy_changed.connect(busy.append)
        with (
            mock.patch.object(batch_apply_module, "take_snapshot", return_value="/tmp/snapshot.qgz"),
            mock.patch.object(batch_apply_module, "project_identity", return_value="project"),
            mock.patch.object(apply_run_module, "project_identity", return_value="project"),
        ):
            loop.confirm_pending()
            self.assertTrue(loop.is_applying)
            self.assertEqual((applied, busy), ([], [True]))
            executor.works[0].progressed.emit(64.0)
            executor.finish()
        self.assertEqual(progress, [-1.0, 64.0])
        self.assertEqual(len(applied), 1)
        self.assertEqual(busy, [True, False])
        self.assertFalse(loop.is_applying)


if __name__ == "__main__":
    unittest.main()
