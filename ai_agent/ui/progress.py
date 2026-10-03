"""The working line at the foot of the conversation, as in Claude Code: dots, the current step, the time.

It lives in the feed under the last message, so it scrolls with the
conversation instead of sitting on the composer.
"""

import math
import time
from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt, QTimer
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style

FRAME_MS = 16
WAVE_SECONDS = 1.1
WAVE_LAG = 0.16
DOTS = 3
DOT = 6
DOT_GAP = 5
BOUNCE = 2.0
SMALLEST = 0.7
WORKING = tr("Working…")
SECONDS = tr("{0} s")
MINUTES = tr("{0} min {1} s")


class WorkingDots(QWidget):
    """Three dots in a soft travelling wave: each swells, brightens and lifts a little in turn.

    Painted every frame from a continuous phase, so the motion is smooth rather than stepped.
    """

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._lit = style.accent(palette)
        self._dim = style.faint(palette)
        self.phase = 0.0
        self.setFixedSize(int(DOTS * DOT + (DOTS - 1) * DOT_GAP), int(DOT + 2 * BOUNCE + 2))

    def set_phase(self, phase: float) -> None:
        self.phase = phase
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        middle = self.height() / 2
        for index in range(DOTS):
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * (self.phase - index * WAVE_LAG))
            painter.setBrush(style.blend(self._dim, self._lit, wave))
            radius = DOT / 2 * (SMALLEST + (1 - SMALLEST) * wave)
            centre_x = index * (DOT + DOT_GAP) + DOT / 2
            centre_y = middle - BOUNCE * wave
            painter.drawEllipse(QRectF(centre_x - radius, centre_y - radius, 2 * radius, 2 * radius))
        painter.end()


class ProgressLine(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._started = 0.0
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 4, 2, 4)
        line.setSpacing(10)
        self._dots = WorkingDots(palette)
        line.addWidget(self._dots, 0, Qt.AlignmentFlag.AlignVCenter)
        self._step = controls.ElidedLabel(WORKING)
        self._step.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(self._step, 1)
        self._elapsed = controls.small("", palette)
        self._elapsed.setWordWrap(False)
        line.addWidget(self._elapsed)
        self._shown_second = -1
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self.hide()

    @property
    def step_text(self) -> str:
        return self._step.text()

    def start(self) -> None:
        self._started = time.monotonic()
        self._step.setText(WORKING)
        self._step.setToolTip(WORKING)
        self._shown_second = 0
        self._elapsed.setText(_duration(0))
        self._dots.set_phase(0.0)
        self._timer.start()
        self.show()

    def step(self, text: str) -> None:
        self._step.setText(text)
        self._step.setToolTip(text)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        self._dots.set_phase(elapsed / WAVE_SECONDS)
        # The text changes once a second; setting it every frame would relayout for nothing.
        if int(elapsed) != self._shown_second:
            self._shown_second = int(elapsed)
            self._elapsed.setText(_duration(elapsed))


def _duration(seconds: float) -> str:
    whole = int(seconds)
    return SECONDS.format(whole) if whole < 60 else MINUTES.format(whole // 60, whole % 60)
