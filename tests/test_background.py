import sys
import types
import unittest
from unittest import mock

from ai_agent.qgis_tools.common import background
from ai_agent.qgis_tools.common.background import STOPPED, Background, InTask, download_progress
from ai_agent.qgis_tools.processing.background_run import ProcessingInBackground

TIMEOUT = "Stopped at the {seconds} s tool timeout."


class Halting(Background):
    def __init__(self, seconds=None, launch_error=None):
        super().__init__(seconds, TIMEOUT)
        self.halts = 0
        self._error = launch_error

    def _launch(self):
        if self._error is not None:
            raise self._error

    def _halt(self):
        self.halts += 1


class BackgroundLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.ended = []
        self.deferred = []
        patcher = mock.patch.object(
            background.QTimer, "singleShot", side_effect=lambda ms, slot: self.deferred.append(slot)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(background._RUNNING.clear)

    def started(self, work):
        work.finished.connect(self.ended.append)
        work.start()
        return work

    def test_a_launch_that_fails_ends_only_after_start_returned(self):
        work = self.started(Halting(launch_error=RuntimeError("no task manager")))
        self.assertEqual(self.ended, [], "finished arrived before start returned")
        self.assertIn(work, background._RUNNING)
        self.deferred[0]()
        self.assertEqual([str(outcome) for outcome in self.ended], ["no task manager"])
        self.assertNotIn(work, background._RUNNING)

    def test_the_time_limit_stops_the_work_and_names_itself(self):
        work = self.started(Halting(seconds=5))
        self.assertEqual(work._limit.started, 1)
        work._limit.fire()
        work.cancel()
        self.assertEqual(work.halts, 1, "a second stop halted the work again")
        work._end({"layers": ["late"]})
        self.assertIsInstance(self.ended[0], TimeoutError)
        self.assertEqual(str(self.ended[0]), "Stopped at the 5 s tool timeout.")

    def test_progress_counts_and_the_outcome_arrive_once_and_stop_at_the_end(self):
        work = self.started(Halting())
        progress, counts = [], []
        work.progressed.connect(progress.append)
        work.counted.connect(counts.append)
        work._report(40)
        work._count(1024)
        work._end({"layers": ["roads"]})
        work._report(90)
        work._count(4096)
        work._end({"layers": ["again"]})
        work.cancel()
        self.assertEqual((progress, counts), ([40.0], [1024]))
        self.assertEqual(self.ended, [{"layers": ["roads"]}])
        self.assertEqual(work.halts, 0, "a stop after the end reached the work")
        self.assertEqual(work._limit.stopped, 1)


class InTaskOutcomeTest(unittest.TestCase):
    def setUp(self):
        self.ended = []
        for patcher in (
            mock.patch.object(background, "QgsApplication"),
            mock.patch.object(background.QgsTask, "cancel", create=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(background._RUNNING.clear)

    def finish(self, work_function, complete):
        work = InTask("download", work_function, complete)
        work.finished.connect(self.ended.append)
        work.start()
        task = work._task
        task.finished(task.run())
        return work

    def test_a_result_that_cannot_be_made_on_the_main_thread_is_the_outcome(self):
        def complete(value):
            raise ValueError("The answer has no features.")

        self.finish(lambda feedback: b"{}", complete)
        self.assertEqual([str(outcome) for outcome in self.ended], ["The answer has no features."])

    def test_a_work_that_raises_ends_with_its_error_not_a_crash(self):
        made = []
        self.finish(lambda feedback: 1 / 0, made.append)
        self.assertEqual(made, [])
        self.assertIsInstance(self.ended[0], ZeroDivisionError)

    def test_a_work_cancelled_by_its_feedback_keeps_nothing(self):
        made = []

        def work(feedback):
            feedback.cancel()
            return "partial answer"

        self.finish(work, made.append)
        self.assertEqual(made, [])
        self.assertEqual([str(outcome) for outcome in self.ended], [STOPPED])

    def test_a_finished_task_whose_report_fails_is_logged_not_raised(self):
        def done(value, error):
            raise RuntimeError("the batch is gone")

        task = background._Worker("download", lambda feedback: "answer", done)
        with mock.patch.object(background.QgsMessageLog, "logMessage") as log:
            task.finished(task.run())
        self.assertIn("RuntimeError", log.call_args.args[0])


class DownloadProgressTest(unittest.TestCase):
    def test_bytes_and_percent_reach_the_feedback_and_stay_within_bounds(self):
        feedback = mock.Mock()
        report = download_progress(feedback)
        report(512, 2048)
        report(4096, 2048)
        report(100, 0)
        report(-5, -1)
        self.assertEqual([item.args[0] for item in feedback.setProcessedCount.call_args_list], [512, 4096, 100, 0])
        self.assertEqual([item.args[0] for item in feedback.setProgress.call_args_list], [25.0, 100.0])


class StopAfterTheWorkTest(unittest.TestCase):
    def test_a_download_stopped_while_its_ending_waits_adds_nothing(self):
        made, ended = [], []
        work = InTask("download", lambda feedback: "answer", lambda value: made.append(value) or {"layers": []})
        work.finished.connect(ended.append)
        with (
            mock.patch.object(background, "QgsApplication"),
            mock.patch.object(background.QgsTask, "cancel", create=True),
        ):
            work.start()
            task = work._task
            self.assertTrue(task.run(), "the work itself ran to its end")
            work.cancel()
            task.finished(True)
        self.assertEqual(made, [], "the answer was turned into layers after the Stop")
        self.assertEqual([str(outcome) for outcome in ended], [STOPPED])

    def test_an_algorithm_stopped_while_its_results_wait_loads_nothing(self):
        loaded, made, ended = [], [], []
        postprocessing = types.ModuleType("processing.gui.Postprocessing")
        postprocessing.handleAlgorithmResults = lambda *args: loaded.append(args)
        modules = {
            "processing": types.ModuleType("processing"),
            "processing.gui": types.ModuleType("processing.gui"),
            "processing.gui.Postprocessing": postprocessing,
        }
        work = ProcessingInBackground("native:centroids", {}, True, lambda outputs: made.append(outputs) or {}, 60)
        work.finished.connect(ended.append)
        work.cancel()
        with mock.patch.dict(sys.modules, modules):
            work._executed(True, {"OUTPUT": "Centroids_id"})
        self.assertEqual((loaded, made), ([], []), "the results were loaded into the project after the Stop")
        self.assertEqual([str(outcome) for outcome in ended], [STOPPED])


if __name__ == "__main__":
    unittest.main()
