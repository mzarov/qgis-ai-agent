"""The status line at the foot of the conversation: the panel's one live compass and a few words.

Working: the needle searches, "Working…", the time runs. A model request that
waits to be retried says so, counting down, until the feed moves on. Waiting for the user:
it tilts slowly, "Waiting for your answer". Done: it settles north once,
"Done in 7 s". Failed: a short shake with a red tip. A stop hides the line.

The current call is named in the open activity list above it, so the line does not repeat it.

It lives in the feed under the last message, so it scrolls with the
conversation instead of sitting on the composer.
"""

import math
import time
from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget

from ai_agent.core.orchestrator.notices import STATUS_DONE, STATUS_FAILED, STATUS_HIDDEN, STATUS_WAITING
from ai_agent.i18n import tr
from ai_agent.ui import compass, controls, style
from ai_agent.ui.durations import format_seconds

# The elapsed time shows whole seconds; a quarter-second tick keeps it on time without busy repaints.
TICK_MS = 250
MARK = 18
# The line's own state while a run is busy; the outcomes come from the orchestrator.
RUNNING = "running"
WORKING = tr("Working…")
WAITING = tr("Waiting for your answer")
DONE_IN = tr("Done in {0}")
RETRY_BUSY = tr("The model is busy · retrying in {0} ({1}/{2})")
RETRY_FAILED = tr("The request failed · retrying in {0} ({1}/{2})")
RETRYING = tr("Retrying… ({0}/{1})")
FAILED = tr("Stopped by an error — the reason is above")
OUTCOMES = {
    STATUS_WAITING: (compass.ASK, WAITING),
    STATUS_DONE: (compass.DONE, DONE_IN),
    STATUS_FAILED: (compass.ERROR, FAILED),
}


class ProgressLine(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._started = 0.0
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 4, 2, 4)
        line.setSpacing(10)
        self.compass = compass.Compass(MARK, palette)
        line.addWidget(self.compass, 0, Qt.AlignmentFlag.AlignVCenter)
        self._step = controls.ElidedLabel(WORKING)
        style.ink(self._step, style.muted(palette))
        line.addWidget(self._step, 1)
        self._elapsed = controls.small("", palette)
        self._elapsed.setWordWrap(False)
        line.addWidget(self._elapsed)
        self._shown_second = -1
        # (wording, deadline, attempt, total) while a request waits to be retried.
        self._retry: tuple[str, float, int, int] | None = None
        self._retry_second = -1
        self.state = STATUS_HIDDEN
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.hide()

    @property
    def step_text(self) -> str:
        return self._step.text()

    def start(self) -> None:
        self.state = RUNNING
        self._started = time.monotonic()
        self._retry = None
        self._say(WORKING)
        self._shown_second = 0
        self._elapsed.setText(format_seconds(0, decimals=0))
        self._elapsed.setVisible(True)
        self.compass.set_state(compass.SEARCH)
        self._timer.start()
        self.show()

    def stop(self) -> None:
        """The agent is no longer busy: hide, unless an outcome already took the line over."""
        self._timer.stop()
        if self.state == RUNNING:
            self.show_outcome(STATUS_HIDDEN)

    def clear_outcome(self) -> None:
        """Another conversation is shown: the last run's outcome belongs to the old one."""
        if self.state != RUNNING:
            self.show_outcome(STATUS_HIDDEN)

    def show_outcome(self, kind: str) -> None:
        """Say how the run stopped working: waiting, done, failed — or hide the line."""
        self._timer.stop()
        self._retry = None
        outcome = OUTCOMES.get(kind)
        if outcome is None:
            self.state = STATUS_HIDDEN
            self.compass.stop()
            self.hide()
            return
        state, text = outcome
        took = format_seconds(time.monotonic() - self._started, decimals=0) if self._started else ""
        shown = text.format(took) if kind == STATUS_DONE else text
        self.state = kind
        self._say(shown)
        self._elapsed.setVisible(False)
        self.compass.set_state(state)
        self.show()

    def show_retry(self, seconds: float, attempt: int, total: int, busy: bool) -> None:
        """The model request waits `seconds` before attempt `attempt` of `total`: say so, counting down."""
        if self.state != RUNNING:
            return
        self._retry = (RETRY_BUSY if busy else RETRY_FAILED, time.monotonic() + seconds, attempt, total)
        self._retry_second = -1
        self._show_retry()

    def resume(self) -> None:
        """Something reached the feed: a retry's note gives way to the plain "Working…"."""
        if self._retry is None:
            return
        self._retry = None
        if self.state == RUNNING:
            self._say(WORKING)

    def _show_retry(self) -> None:
        if self._retry is None:
            return
        wording, deadline, attempt, total = self._retry
        left = max(0, math.ceil(deadline - time.monotonic()))
        if left == self._retry_second:
            return
        self._retry_second = left
        if left:
            self._say(wording.format(format_seconds(left, decimals=0), attempt, total))
        else:
            self._say(RETRYING.format(attempt, total))

    def _say(self, text: str) -> None:
        self._step.setText(text)
        self._step.setToolTip(text)

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        # The text changes once a second; setting it every frame would relayout for nothing.
        if int(elapsed) != self._shown_second:
            self._shown_second = int(elapsed)
            self._elapsed.setText(format_seconds(elapsed, decimals=0))
        self._show_retry()
