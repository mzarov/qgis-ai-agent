import math
import time
from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget

from ai_agent.core.orchestrator.notices import (
    RUN_CHECK,
    RUN_LOOK_INTO,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_HIDDEN,
    STATUS_WAITING,
)
from ai_agent.i18n import tr
from ai_agent.ui import compass, controls, style
from ai_agent.ui.durations import format_seconds

TICK_MS = 250
MARK = 18
RUNNING = "running"
WORKING = tr("Working…")
CHECKING = tr("Checking the changes…")
LOOKING_INTO = tr("Looking into the failure…")
WAITING = tr("Waiting for your answer")
DONE_IN = tr("Done in {0}")
RETRY_BUSY = tr("The model is busy · retrying in {0} ({1}/{2})")
RETRY_FAILED = tr("The request failed · retrying in {0} ({1}/{2})")
RETRYING = tr("Retrying… ({0}/{1})")
FAILED = tr("Stopped by an error — the reason is above")
SUMMARY = "{0} · {1}"
OUTCOMES = {
    STATUS_WAITING: (compass.ASK, WAITING),
    STATUS_DONE: (compass.DONE, DONE_IN),
    STATUS_FAILED: (compass.ERROR, FAILED),
}


WORKING_BY_KIND = {RUN_CHECK: CHECKING, RUN_LOOK_INTO: LOOKING_INTO}


class ProgressLine(QWidget):
    def __init__(self, palette: Any):
        super().__init__()
        self._started = 0.0
        self._counting = False
        self._working = WORKING
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
        self._retry: tuple[str, float, int, int] | None = None
        self._retry_second = -1
        self.state = STATUS_HIDDEN
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def begin(self) -> None:
        self._started = time.monotonic()
        self._counting = True

    def start(self, kind: str = "") -> None:
        self.state = RUNNING
        if not self._counting:
            self._started = time.monotonic()
            self._counting = True
        self._retry = None
        self._working = WORKING_BY_KIND.get(kind, WORKING)
        self._say(self._working)
        self._shown_second = 0
        self._elapsed.setText(format_seconds(0, decimals=0))
        self._elapsed.setVisible(True)
        self.compass.set_state(compass.SEARCH)
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        if self.state == RUNNING:
            self._hide()

    def clear_outcome(self) -> None:
        if self.state != RUNNING:
            self.show_outcome(STATUS_HIDDEN)

    def show_outcome(self, kind: str, summary: str = "") -> None:
        self._timer.stop()
        self._retry = None
        outcome = OUTCOMES.get(kind)
        if kind != STATUS_DONE:
            self._counting = False
        if outcome is None:
            self._hide()
            return
        state, text = outcome
        took = format_seconds(time.monotonic() - self._started, decimals=0) if self._started else ""
        shown = text.format(took) if kind == STATUS_DONE else text
        if kind == STATUS_DONE and summary:
            shown = SUMMARY.format(shown, summary)
        self.state = kind
        self._say(shown)
        self._elapsed.setVisible(False)
        self.compass.set_state(state)
        self.show()

    def _hide(self) -> None:
        self.state = STATUS_HIDDEN
        self.compass.stop()
        self.hide()

    def show_retry(self, seconds: float, attempt: int, total: int, busy: bool) -> None:
        if self.state != RUNNING:
            return
        self._retry = (RETRY_BUSY if busy else RETRY_FAILED, time.monotonic() + seconds, attempt, total)
        self._retry_second = -1
        self._show_retry()

    def resume(self) -> None:
        if self._retry is None:
            return
        self._retry = None
        if self.state == RUNNING:
            self._say(self._working)

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
        if int(elapsed) != self._shown_second:
            self._shown_second = int(elapsed)
            self._elapsed.setText(format_seconds(elapsed, decimals=0))
        self._show_retry()
