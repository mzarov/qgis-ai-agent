import unittest

from ai_agent.config import limits
from ai_agent.qgis_tools.processing import run_processing
from ai_agent.qgis_tools.processing.deadline import DeadlineFeedback


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class DeadlineFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.feedback = DeadlineFeedback(30, self.clock)

    def test_a_report_in_time_changes_nothing(self):
        self.clock.now += 29
        self.feedback.pushInfo("halfway")
        self.assertFalse(self.feedback.timed_out)
        self.assertFalse(self.feedback.isCanceled())

    def test_the_first_report_past_the_limit_cancels_the_algorithm(self):
        self.clock.now += 31
        self.feedback.setProgressText("still going")
        self.assertTrue(self.feedback.timed_out)
        self.assertTrue(self.feedback.isCanceled())
        self.assertIn("30 s", self.feedback.timeout_message())
        self.assertIn("Settings", self.feedback.timeout_message())


class TimedOutRunTest(unittest.TestCase):
    def setUp(self):
        self.tool = run_processing.RunProcessingTool()
        self.saved = (run_processing.RunProcessingTool._prepare, run_processing.RunProcessingTool._get_runner)
        self.saved_limit = limits.tool_seconds
        self.saved_names = run_processing.destination_parameter_names
        algorithm = type("Algorithm", (), {"id": lambda self: "native:buffer"})()
        run_processing.RunProcessingTool._prepare = staticmethod(lambda params: (algorithm, {}))
        run_processing.destination_parameter_names = lambda algorithm: []
        limits.tool_seconds = lambda: 0

    def tearDown(self):
        run_processing.RunProcessingTool._prepare, run_processing.RunProcessingTool._get_runner = self.saved
        limits.tool_seconds = self.saved_limit
        run_processing.destination_parameter_names = self.saved_names

    def _runner(self, raises: bool):
        def run(algorithm_id, parameters, feedback=None):
            feedback.pushInfo("working")
            if raises:
                raise RuntimeError("Process was canceled")
            return {}

        run_processing.RunProcessingTool._get_runner = staticmethod(lambda load_output: run)

    def test_a_cancelled_algorithm_that_raises_reports_the_timeout(self):
        self._runner(raises=True)
        with self.assertRaises(TimeoutError) as caught:
            self.tool.execute({"algorithm_id": "native:buffer", "parameters": {}})
        self.assertIn("tool timeout", str(caught.exception))

    def test_a_cancelled_algorithm_that_returns_still_fails(self):
        self._runner(raises=False)
        with self.assertRaises(TimeoutError):
            self.tool.execute({"algorithm_id": "native:buffer", "parameters": {}})


class LimitsTest(unittest.TestCase):
    def test_values_out_of_range_are_clamped_and_garbage_falls_back(self):
        self.assertEqual(limits._clamped("3", 40, 5, 100), 5)
        self.assertEqual(limits._clamped(1000, 40, 5, 100), 100)
        self.assertEqual(limits._clamped("many", 40, 5, 100), 40)
        self.assertEqual(limits._clamped(None, 120, 15, 600), 120)


if __name__ == "__main__":
    unittest.main()
