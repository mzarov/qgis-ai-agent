"""The line above the composer while the agent works: a pulsing dot, the current step, the count."""

from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget

from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, style

PULSE_MS = 600
DOT = 8
WORKING = tr("Working…")


class PulseDot(QWidget):
    """A dot painted by hand; restyling a label twice a second churned the style engine."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(DOT, DOT)
        self.colour = ""

    def set_colour(self, name: str) -> None:
        if name != self.colour:
            self.colour = name
            self.update()

    def paintEvent(self, _event: Any) -> None:
        if not self.colour:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colour))
        painter.drawEllipse(QRectF(0, 0, DOT, DOT))
        painter.end()


class ProgressLine(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._steps = 0
        self._lit = True
        line = QHBoxLayout(self)
        line.setContentsMargins(4, 0, 4, 6)
        line.setSpacing(8)
        self._dot = PulseDot()
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
        self._dot.set_colour(colour.name())
