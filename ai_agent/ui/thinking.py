"""A reasoning step on the work trace: "Thinking" while it streams, "Thought" with its time after.

The line opens a sunken box with the text, the chevron after the title turning
as the box grows or shrinks; it is open while the reasoning streams and folds
when it ends, so the trace stays a list of steps. A reopened conversation
restores the text and the time folded, without animation.
"""

import time
from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import folding, style
from ai_agent.ui.durations import format_seconds

TEXT_FONT_SCALE = 0.96
SMALL = 0.92
REPAINT_INTERVAL_MS = 80
SHORTEST_SHOWN = 0.1
CHEVRON = 12
BOX_GAP = 6
BOX_RADIUS = 6
BOX_PADDING = "8px 10px"
THINKING_TITLE = tr("Thinking")
THOUGHT_TITLE = tr("Thought")


class ClickLine(QWidget):
    """A line that is clicked as a whole."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ThinkingBlock(QFrame):
    """The reasoning row's content: a clickable line with the time on the right, and the text box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self._palette = self.palette()
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 1, 0, 0)
        column.setSpacing(0)
        self._line = ClickLine()
        self._line.clicked.connect(self._toggle)
        line = QHBoxLayout(self._line)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self._title = QLabel()
        style.ink(self._title, style.muted(palette))
        line.addWidget(self._title)
        self._chevron = folding.Chevron(palette, CHEVRON)
        line.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch(1)
        self.time = QLabel()
        style.scale_font(self.time, SMALL)
        style.ink(self.time, style.faint(palette))
        line.addWidget(self.time)
        column.addWidget(self._line)
        self._clip = folding.ClipBox(self._build_body(palette))
        column.addWidget(self._clip)
        # Room the row gives beyond the line and the box goes below them: the title never moves.
        column.addStretch(1)
        self._recorded: float | None = None
        self._text = ""
        self._started = time.monotonic()
        self._deliveries = 0
        self._finished = False
        self.expanded = False
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(REPAINT_INTERVAL_MS)
        self._repaint.timeout.connect(self._render_text)
        self.set_expanded(True, animate=False)
        self._refresh()

    def _build_body(self, palette: Any) -> QWidget:
        """The sunken box, in a holder whose top margin is the gap: it opens with the box, no jump."""
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, BOX_GAP, 0, 0)
        self._body = QLabel()
        self._body.setTextFormat(Qt.TextFormat.PlainText)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._body.setStyleSheet(
            f"QLabel {{ color: {style.css_color(style.muted(palette))};"
            f" background: {style.css_color(style.sunken(palette))};"
            f" border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f" border-radius: {BOX_RADIUS}px; padding: {BOX_PADDING}; }}"
        )
        style.scale_font(self._body, TEXT_FONT_SCALE)
        box.addWidget(self._body)
        return holder

    def _toggle(self) -> None:
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        self.expanded = expanded
        self._chevron.set_open(expanded, animate)
        self._clip.set_open(expanded, animate)

    def finish_folding(self) -> None:
        """End a fold or a turn at once, as a screenshot wants it."""
        self._clip.finish()
        self._chevron.finish()

    def restore(self, text: str, seconds: Any = None) -> None:
        """A saved reasoning step: its text and time, folded at once."""
        self._text = text
        self._render_text()
        self._finished = True
        self._recorded = float(seconds) if isinstance(seconds, (int, float)) else None
        self.set_expanded(False, animate=False)
        self._refresh()

    def append(self, delta: str) -> None:
        self._text += delta
        self._deliveries += 1
        if self._deliveries == 1:
            self._render_text()
            self._refresh()
        elif not self._repaint.isActive():
            self._repaint.start()

    def _render_text(self) -> None:
        self._body.setText(self._text)

    @property
    def _watched_live(self) -> bool:
        return self._deliveries > 1

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._repaint.stop()
        self._render_text()
        self.set_expanded(False)
        self._refresh()

    def _refresh(self) -> None:
        self._title.setText(THOUGHT_TITLE if self._finished else THINKING_TITLE)
        if self._recorded is not None:
            self.time.setText(format_seconds(self._recorded) if self._recorded >= SHORTEST_SHOWN else "")
            return
        took = time.monotonic() - self._started
        # "0.0 s" claims a measurement that did not happen: reasoning that arrived in one burst.
        shown = self._finished and self._watched_live and took >= SHORTEST_SHOWN
        self.time.setText(format_seconds(took) if shown else "")
