import unittest
from unittest import mock

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent import apply_run as apply_run_module
from ai_agent.core.agent import batch_apply as batch_apply_module
from ai_agent.core.agent import executor as executor_module
from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.prompts import APPLY_NOW_TOOL
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.base import RESULT_IMAGE_KEY, RESULT_VISUAL_KEY


class FakeWork(QObject):
    progressed = pyqtSignal(float)
    counted = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class BackgroundExecutor:
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
        self.executor.works[0].progressed.emit(50.0)
        self.executor.finish()
        self.assertEqual(self.finished, [])
        self.assertEqual(self.progress, [(-1.0, 0)])
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing"])

    def test_a_step_that_raises_frees_the_batch_for_the_next_plan(self):
        class Raising(BackgroundExecutor):
            def run(self, call):
                if call.name == "set_symbol":
                    raise RuntimeError("renderer crashed")
                return super().run(call)

        self.batch._executor = Raising()
        self.batch._calls = calls("set_opacity", "set_symbol", "configure_layer")
        with self.assertRaisesRegex(RuntimeError, "renderer crashed"):
            self.apply()
        self.assertFalse(self.batch.is_applying)
        self.assertFalse(self.batch)
        self.assertEqual(self.batch.executing_tool, "")
        self.batch._calls = calls("set_opacity")
        self.assertEqual([result.ok for result in self.apply()], [True])

    def test_a_background_step_that_reports_twice_is_counted_once(self):
        self.apply()
        call, done = self.executor._waiting[0]
        self.executor.finish()
        done(ToolResult(call=call, payload={"again": True}))
        self.assertEqual(len(self.finished), 1)
        self.assertEqual([result.payload for result in self.finished[0]], [{"ok": True}, {"done": True}, {"ok": True}])

    def test_a_report_that_cannot_be_shown_stops_the_batch_without_running_more(self):
        def on_finish(call, result):
            if call.name == "run_processing":
                raise RuntimeError("the feed is gone")

        self.batch.apply(lambda call: None, on_finish, "project", self.finished.append)
        self.executor.finish()
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing"])
        self.assertEqual(len(self.finished), 1)
        self.assertFalse(self.batch.is_applying)


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


class LoopApplyFailureTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.executor = BackgroundExecutor()
        self.loop._batch._executor = self.executor
        self.applied, self.interrupted, self.busy, self.aborted = [], [], [], []
        self.loop.applied.connect(self.applied.append)
        self.loop.apply_interrupted.connect(self.interrupted.append)
        self.loop.busy_changed.connect(self.busy.append)
        self.loop.aborted.connect(lambda: self.aborted.append(True))
        for target, name, value in (
            (batch_apply_module, "take_snapshot", "/tmp/snapshot.qgz"),
            (batch_apply_module, "project_identity", "project"),
            (apply_run_module, "project_identity", "project"),
        ):
            patcher = mock.patch.object(target, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unloading_during_a_long_step_reports_to_nobody(self):
        self.loop._batch._calls = calls("run_processing", "set_symbol")
        self.loop.confirm_pending()
        self.loop.shutdown()
        self.assertTrue(self.executor.works[0].cancelled)
        self.assertFalse(self.loop.is_applying)
        self.executor.finish(ok=False)
        self.assertEqual((self.applied, self.interrupted), ([], []))
        self.assertEqual(self.executor.ran, ["run_processing"])

    def test_cancel_during_a_long_step_stops_it_and_reports_the_partial_apply(self):
        self.loop._batch._calls = calls("set_opacity", "run_processing", "set_symbol")
        self.loop.confirm_pending()
        self.loop.cancel_pending()
        self.assertTrue(self.executor.works[0].cancelled)
        self.assertEqual((self.busy, self.aborted), ([True, False], [True]))
        self.executor.finish(ok=False)
        self.assertEqual(self.applied, [])
        self.assertEqual([result.ok for result in self.interrupted[0]], [True, False, False])
        self.assertEqual(self.interrupted[0][2].payload["status"], "skipped")
        self.assertEqual(self.executor.ran, ["set_opacity", "run_processing"])

    def test_an_exception_while_applying_frees_the_loop(self):
        class Raising(BackgroundExecutor):
            def run(self, call):
                raise RuntimeError("renderer crashed")

        self.loop._batch._executor = Raising()
        self.loop._batch._calls = calls("set_opacity")
        with self.assertRaisesRegex(RuntimeError, "renderer crashed"):
            self.loop.confirm_pending()
        self.assertEqual(self.busy, [True, False])
        self.assertFalse(self.loop.is_applying)
        self.assertFalse(self.loop.has_pending_writes)
        self.assertEqual(self.loop.active_apply_tool, "")


class StagedSnapshotFailureTest(unittest.TestCase):
    def test_the_model_hears_why_and_the_resumed_run_can_be_stopped(self):
        loop = AgentLoop()
        write = ToolCall(id="write", name="set_opacity", arguments={})
        control = ToolCall(id="apply", name=APPLY_NOW_TOOL, arguments={})
        loop._transcript.add_results(
            [
                ToolResult(call=write, payload={"status": "queued"}),
                ToolResult(call=control, payload={"status": "awaiting_user"}),
            ],
            "native",
        )
        loop._batch._calls = [write]
        loop._staged = True
        loop._stage_call = control
        resumed, busy, staged, applied = [], [], [], []
        loop._request_step = lambda: resumed.append(loop.is_applying)
        loop.busy_changed.connect(busy.append)
        loop.stage_applied.connect(staged.append)
        loop.applied.connect(applied.append)
        reason = "QGIS has an active edit buffer on: roads."
        with (
            mock.patch.object(batch_apply_module, "take_snapshot", return_value=""),
            mock.patch.object(batch_apply_module, "snapshot_error", return_value=reason),
        ):
            loop.confirm_pending()

        self.assertEqual([result.payload["error"] for result in staged[0]], [reason])
        self.assertEqual((resumed, applied), ([False], []))
        self.assertEqual(busy, [True], "the run goes on with the model, so Stop must be offered")
        self.assertFalse(loop.has_pending_writes)
        rendered = loop._transcript.build_messages("S")
        self.assertIn("edit buffer", rendered[1]["content"])
        self.assertIn("failed", rendered[2]["content"])


class ExecutorStartTest(unittest.TestCase):
    def setUp(self):
        self.work = FakeWork()
        self.ended = []

    def start(self, name="run_processing"):
        with mock.patch.object(executor_module, "start_tool", return_value=self.work):
            return ToolExecutor().start(ToolCall(id="long", name=name, arguments={}), self.ended.append)

    def test_a_long_step_starts_its_work_and_hands_back_the_outcome(self):
        self.assertIs(self.start(), self.work)
        self.assertTrue(self.work.started)
        legend = {"kind": "legend"}
        self.work.finished.emit({"result_layer_name": "Buffered", RESULT_IMAGE_KEY: "aGk=", RESULT_VISUAL_KEY: legend})
        result = self.ended[0]
        self.assertTrue(result.ok)
        self.assertEqual(result.payload, {"result_layer_name": "Buffered", "image_attached": True})
        self.assertEqual((result.image, result.visual, result.egress), ("aGk=", legend, "feature_values"))

    def test_a_work_that_ends_with_an_exception_is_a_failed_step(self):
        self.start()
        self.work.finished.emit(TimeoutError("Stopped at the 0 s tool timeout."))
        self.assertFalse(self.ended[0].ok)
        self.assertEqual(self.ended[0].payload["error"], "Stopped at the 0 s tool timeout.")

    def test_a_work_that_reports_an_error_is_a_failed_step_without_its_visual(self):
        self.start()
        self.work.finished.emit({"error": "INPUT is empty", RESULT_VISUAL_KEY: {"x": 1}})
        self.assertFalse(self.ended[0].ok)
        self.assertIsNone(self.ended[0].visual)

    def test_an_unknown_tool_or_a_refused_start_leaves_the_step_to_the_main_thread(self):
        self.assertIsNone(self.start("no_such_tool"))
        call = ToolCall(id="x", name="run_processing", arguments={})
        with mock.patch.object(executor_module, "start_tool", side_effect=ValueError("bad parameters")):
            self.assertIsNone(ToolExecutor().start(call, self.ended.append))
        with mock.patch.object(executor_module, "start_tool", return_value=None):
            self.assertIsNone(ToolExecutor().start(call, self.ended.append))
        self.assertEqual(self.ended, [])

    def test_a_refused_start_still_runs_the_step_through_execute(self):
        batch = WriteBatch(ToolExecutor())
        batch._calls = [ToolCall(id="x", name="run_processing", arguments={})]
        with (
            mock.patch.object(executor_module, "start_tool", side_effect=RuntimeError("no task manager")),
            mock.patch.object(executor_module, "execute_tool", return_value={"result_layer_name": "Buffered"}),
            mock.patch.object(apply_run_module, "project_identity", return_value="project"),
        ):
            results = batch.apply(lambda call: None, lambda call, result: None, "project")
        self.assertEqual([result.payload for result in results], [{"result_layer_name": "Buffered"}])


if __name__ == "__main__":
    unittest.main()
