import unittest
from unittest import mock

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.core.orchestrator import notices
from ai_agent.ui import progress


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class DoneTimeTest(unittest.TestCase):
    """The time on "Done in N s" runs from the user's last action, not from the last phase that started."""

    def setUp(self):
        self.clock = Clock()
        patcher = mock.patch.object(progress.time, "monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.line = progress.ProgressLine(QWidget().palette())

    def done_text(self):
        self.line.show_outcome(notices.STATUS_DONE)
        return self.line.step_text

    def test_auto_mode_counts_the_run_the_apply_and_the_check(self):
        # Seen: "Done in 0 s" after a run of a minute, because the apply restarted the clock.
        self.line.begin()
        self.line.start()
        self.clock.now += 50
        self.line.stop()
        self.line.start()
        self.clock.now += 2
        self.line.stop()
        self.assertIn("52", self.done_text())
        self.line.start("check")
        self.clock.now += 8
        self.line.stop()
        self.assertIn("1 min", self.done_text(), "the check after Apply is part of the same work")

    def test_waiting_ends_the_work_and_apply_starts_anew(self):
        self.line.begin()
        self.line.start()
        self.clock.now += 30
        self.line.show_outcome(notices.STATUS_WAITING)
        self.clock.now += 600
        self.line.begin()
        self.line.start()
        self.clock.now += 3
        self.assertIn("3", self.done_text())
        self.assertNotIn("min", self.line.step_text, "the minutes before Apply was pressed are not work")

    def test_work_nobody_announced_keeps_its_own_time(self):
        self.line.start()
        self.clock.now += 4
        self.assertIn("4", self.done_text())


if __name__ == "__main__":
    unittest.main()
