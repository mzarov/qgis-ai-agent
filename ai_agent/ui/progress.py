"""The line above the composer while the agent works: a pulsing dot, the current step, the count."""

from typing import Any

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QWidget

from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, style

PULSE_MS = 600
DOT = 8
WORKING = tr("Working…")


class ProgressLine(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._steps = 0
        self._lit = True
        line = QHBoxLayout(self)
        line.setContentsMargins(4, 0, 4, 6)
        line.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(DOT, DOT)
        line.addWidget(self._dot)
        self._step = controls.small(WORKING, palette)
        self._step.setWordWrap(False)
        self._step.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(self._step, 1)
        self._count = controls.small("", palette)
        self._count.setWordWrap(False)
        line.addWidget(self._count)
        self._timer = QTimer(self)
        self._timer.setInterval(PULSE_MS)
        self._timer.timeout.connect(self._pulse)
        self._paint_dot()
        self.hide()

    @property
    def step_text(self) -> str:
        return self._step.text()

    def start(self) -> None:
        self._steps = 0
        self._step.setText(WORKING)
        self._count.setText("")
        self._timer.start()
        self.show()

    def step(self, text: str) -> None:
        self._steps += 1
        self._step.setText(text)
        self._count.setText(tr_n("%n step(s)", self._steps))

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _pulse(self) -> None:
        self._lit = not self._lit
        self._paint_dot()

    def _paint_dot(self) -> None:
        accent = style.accent(self._palette)
        colour = accent if self._lit else style.soft(self._palette, accent)
        self._dot.setStyleSheet(f"QLabel {{ background: {style.css_color(colour)}; border-radius: {DOT // 2}px; }}")
