"""A step working off the main thread: a Stop keeps nothing, even one that comes after the work itself ended."""

import sys
import types
import unittest
from unittest import mock

from ai_agent.qgis_tools.common import background
from ai_agent.qgis_tools.common.background import STOPPED, InTask
from ai_agent.qgis_tools.processing.background_run import ProcessingInBackground


class StopAfterTheWorkTest(unittest.TestCase):
    """QGIS calls a task's `finished` on the main thread after its `run` returned: a Stop can fall in between."""

    def test_a_download_stopped_while_its_ending_waits_adds_nothing(self):
        made, ended = [], []
        work = InTask("download", lambda feedback: "answer", lambda value: made.append(value) or {"layers": []})
        work.finished.connect(ended.append)
        # No task manager: the test plays its part, run() in the worker and then finished() on the main thread.
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
