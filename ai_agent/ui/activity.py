"""One turn's tool calls and reasoning, folded the way Claude Code folds them.

Collapsed, the group is a single muted line, "4 actions ›". Opened, its rows sit
in a hairline list, one per call, with the reasoning as a row of its own. Success
is the quiet default and carries no mark; only a failed or rejected call does.
"""

from html import escape
from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr_n
from ai_agent.ui import style
from ai_agent.ui.disclosure import Disclosure

PENDING = "●"
DONE = ""
FAILED = "✕"
REJECTED = "⊘"
RECOVERED = "↺"
NOTE = "· {0}"
CLOSING = {"'": "'", '"': '"', "«": "»", "“": "”"}
STEP_FONT_SCALE = 0.95
LIST_PAD = 12
ROW_PAD = 8
HEADER_GAP = 6


class ActivityList(QWidget):
    """The rows of a group, framed by a painted hairline once there is a call to list.

    A reasoning-only turn stays a bare line: a box around a single fold line would
    be a frame with nothing to frame.
    """

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._border = style.hairline(palette)
        self.framed = False
        self.items: list[QWidget] = []
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)

    def set_framed(self, framed: bool) -> None:
        if framed == self.framed:
            return
        self.framed = framed
        pad = LIST_PAD if framed else 0
        self.rows.setContentsMargins(pad, 0, pad, 0)
        self.update()

    def add_row(self, widget: QWidget) -> None:
        if self.items:
            self._add(Separator(self._border))
        widget.setContentsMargins(0, ROW_PAD, 0, ROW_PAD)
        self._add(widget)

    def _add(self, widget: QWidget) -> None:
        self.items.append(widget)
        self.rows.addWidget(widget)

    def paintEvent(self, _event: Any) -> None:
        if not self.framed:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._border))
        pen.setWidthF(style.HAIRLINE)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = style.HAIRLINE / 2
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.drawRoundedRect(rect, style.CARD_RADIUS, style.CARD_RADIUS)
        painter.end()


class Separator(QWidget):
    def __init__(self, colour: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(style.HAIRLINE)
        style.fill(self, colour)


class ActivityGroup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(HEADER_GAP)
        self._header = Disclosure(palette)
        self._toggle = self._header.toggle
        self._title = self._header.title
        self._status = QLabel()
        self._status.setStyleSheet("border: none;")
        self._header.add_note(self._status)
        self._header.toggled.connect(self._on_toggled)
        column.addWidget(self._header)
        self._steps_holder = ActivityList(palette)
        column.addWidget(self._steps_holder)
        self._count = 0
        self._extras = 0
        self._pending = 0
        self._failures = 0
        self._rejected = False
        self._closed = False
        self._steps_holder.setVisible(False)
        self._refresh()

    def add_step(self, text: str) -> QWidget:
        row = StepRow(text, self.palette())
        self._steps_holder.add_row(row)
        self._count += 1
        self._pending += 1
        self._steps_holder.set_framed(True)
        self._refresh()
        return row

    def add_widget(self, widget: QWidget) -> None:
        self._steps_holder.add_row(widget)
        self._extras += 1
        self._refresh()

    def reveal(self) -> None:
        self._toggle.setChecked(True)
        self._steps_holder.setVisible(True)

    def rest(self) -> None:
        self._closed = True
        self._toggle.setChecked(False)
        if not self._count:
            # A reasoning-only turn has no header to reopen it from: its row stays.
            self._steps_holder.setVisible(self._extras > 0)
        self._refresh()

    def mark_step(self, row: "StepRow", ok: bool) -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.set_state(DONE if ok else FAILED)
        if not ok:
            self._failures += 1
        self._refresh()

    def mark_rejected(self, row: "StepRow") -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.set_state(REJECTED)
        self._rejected = True
        self._refresh()

    def _refresh(self) -> None:
        palette = self.palette()
        self._header.setVisible(bool(self._count))
        self._title.setText(tr_n("%n action(s)", self._count))
        if self._pending and not self._closed:
            marker, colour = PENDING, style.muted(palette)
        elif self._failures:
            marker, colour = NOTE.format(tr_n("%n failed", self._failures)), style.danger(palette)
        elif self._rejected:
            marker, colour = RECOVERED, style.warning(palette)
        else:
            marker, colour = DONE, style.muted(palette)
        self._status.setText(marker)
        self._status.setVisible(marker not in (DONE, PENDING))
        self._status.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")

    def _on_toggled(self, expanded: bool) -> None:
        if self._count:
            self._steps_holder.setVisible(expanded)


class StepRow(QWidget):
    """One call: the wording muted, its own values bright, a mark only when it did not succeed."""

    def __init__(self, text: str, palette, parent=None):
        super().__init__(parent)
        self.setStyleSheet("border: none;")
        self._palette = palette
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.state = PENDING
        self._label = QLabel()
        markup = step_markup(text, palette)
        self._label.setTextFormat(Qt.TextFormat.PlainText if markup is None else Qt.TextFormat.RichText)
        self._label.setText(_without_period(str(text)) if markup is None else markup)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        font = self._label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        self._label.setFont(font)
        row.addWidget(self._label, 1)

        self._marker = QLabel()
        self._marker.setFont(font)
        self._marker.setVisible(False)
        row.addWidget(self._marker, 0, Qt.AlignmentFlag.AlignTop)

    def set_state(self, marker: str) -> None:
        self.state = marker
        self._marker.setText(marker)
        self._marker.setVisible(bool(marker))
        colour = style.warning(self._palette) if marker == REJECTED else style.danger(self._palette)
        self._marker.setStyleSheet(f"color: {style.css_color(colour)};")


def step_markup(text: str, palette: Any) -> str | None:
    """Rich text for a summary with marked values, or None to show it as plain text.

    Every span is escaped: the values come from the model, and a layer named
    `<img src=…>` must read as its name, not render.
    """
    parts = list(getattr(text, "parts", ()))
    if not any(marked for _, marked in parts):
        return None
    last, marked = parts[-1]
    if not marked:
        parts[-1] = (_without_period(last), False)
    bright = style.css_color(style.text(palette))
    return "".join(
        f'<span style="color: {bright};">{escape(span, quote=False)}</span>' if marked else escape(span, quote=False)
        for span, marked in _unquoted(parts)
    )


def _without_period(text: str) -> str:
    # A row is a label, not a sentence; an ellipsis is kept, it means "cut".
    return text[:-1] if text.endswith(".") and not text.endswith("..") else text


def _unquoted(parts: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    # A bright value already stands out; the quotes the wording put around it are noise.
    for index in range(1, len(parts) - 1):
        span, marked = parts[index]
        before, after = parts[index - 1][0], parts[index + 1][0]
        if marked and before and after and CLOSING.get(before[-1]) == after[0]:
            parts[index - 1] = (before[:-1], False)
            parts[index + 1] = (after[1:], False)
    return parts
