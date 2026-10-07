"""One turn's tool calls and reasoning as the design's "work trace": a quiet timeline above the answer.

Not a card. A header line — a chevron, "Activity · 5 steps" (while working
"Working · step 3"), the time on the right — folds the list. Each step is a row
on a timeline: a 16 px glyph in the faint ink with a hairline running down to
the next step, the call's wording muted and its own values bright, a second
line saying what it found, and the step's time on the right. The running step
pulses a small accent ring instead of its glyph. Reasoning and the user's
choice on a question card are rows of their own. Success carries no mark; a
failed step shows its reason in the danger colour.
"""

import time
from html import escape
from typing import Any

from qgis.PyQt.QtCore import QPointF, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QPainter, QPen
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.config import personal
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, icons, style
from ai_agent.ui.durations import format_seconds

PENDING = "●"
DONE = ""
FAILED = "✕"
REJECTED = "⊘"
CLOSING = {"'": "'", '"': '"', "«": "»", "“": "”"}
WORKING = tr("Working · step {0}")
SKILL_TAG = tr("skill")
CHOSE = tr("You chose")
CHOICE = "choice"
KNOWLEDGE = "knowledge"
# The person glyph marks the user's own answer; the skills keep their icons, all in the faint ink.
GLYPH_ROLES = {CHOICE: "personalisation"}
GLYPH = 16
GLYPH_BOX = 20
COLUMN_GAP = 8
ROW_BOTTOM = 10
# The hairline to the next step runs down the glyph column's middle, from just under the glyph.
LINE_X = 9.5
LINE_TOP = 21
HEADER_GAP = 8
GROUP_BOTTOM = 8
SMALL = 0.92
CHEVRON = 12
TAG_PADDING = "0 5px"
TAG_RADIUS = 4
PULSE = 9
PULSE_PEN = 1.5
PULSE_MS = 1200
PULSE_LOW = 0.35
# A step faster than this shows no time: "0.0 s" claims a measurement that says nothing.
SHORTEST_SHOWN = 0.05


class TraceHeader(QWidget):
    """The fold line: chevron, title, failures, and the turn's time on the right; the whole line clicks."""

    toggled = pyqtSignal(bool)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.expanded = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.chevron = QLabel()
        self.chevron.setFixedSize(CHEVRON, CHEVRON)
        line.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = controls.ElidedLabel()
        style.scale_font(self.title, SMALL)
        line.addWidget(self.title, 1)
        self.status = QLabel()
        style.scale_font(self.status, SMALL)
        self.status.setVisible(False)
        line.addWidget(self.status)
        self.time = QLabel()
        style.scale_font(self.time, SMALL)
        line.addWidget(self.time)
        self._ink(style.faint(palette))
        self._draw_chevron()

    def set_expanded(self, expanded: bool) -> None:
        if expanded != self.expanded:
            self.expanded = expanded
            self._draw_chevron()
            self.toggled.emit(expanded)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_expanded(not self.expanded)

    def enterEvent(self, event: Any) -> None:
        self._ink(style.muted(self._palette))
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._ink(style.faint(self._palette))
        super().leaveEvent(event)

    def _ink(self, colour: Any) -> None:
        style.ink(self.title, colour)
        style.ink(self.time, colour)

    def _draw_chevron(self) -> None:
        icon = icons.drawn("expanded" if self.expanded else "collapsed", style.faint(self._palette), CHEVRON)
        if icon is not None:
            self.chevron.setPixmap(icon.pixmap(CHEVRON, CHEVRON))


class PulseRing(QWidget):
    """The running step's mark: a small accent ring whose opacity breathes."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.opacity = 1.0
        self.setFixedSize(GLYPH_BOX, GLYPH_BOX)
        self._breath = QVariantAnimation(self)
        self._breath.setDuration(PULSE_MS)
        self._breath.setKeyValueAt(0.0, 1.0)
        self._breath.setKeyValueAt(0.5, PULSE_LOW)
        self._breath.setKeyValueAt(1.0, 1.0)
        self._breath.setLoopCount(-1)
        # A bound method: Qt drops it when the ring is deleted with its row.
        self._breath.valueChanged.connect(self._breathe)
        self._breath.start()

    def stop(self) -> None:
        self._breath.stop()
        self._breathe(1.0)

    def _breathe(self, value: Any) -> None:
        self.opacity = float(value)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)
        painter.setPen(QPen(style.accent(self._palette), PULSE_PEN))
        painter.setBrush(QBrush(style.soft(self._palette, style.accent(self._palette))))
        radius = (PULSE - PULSE_PEN) / 2
        painter.drawEllipse(QPointF(GLYPH_BOX / 2, GLYPH_BOX / 2), radius, radius)
        painter.end()


class ThinkingDots(QWidget):
    """Three dots: the glyph of a reasoning step."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._colour = style.faint(palette)
        self.setFixedSize(GLYPH_BOX, GLYPH_BOX)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._colour))
        for x in (6.5, 10.0, 13.5):
            painter.drawEllipse(QPointF(x, GLYPH_BOX / 2), 1.1, 1.1)
        painter.end()


class TraceRow(QWidget):
    """A row on the timeline: glyph, content, time; the hairline down to the next row is painted here."""

    def __init__(self, glyph: QWidget, content: QWidget, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.connected = False
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(0, 0, 0, ROW_BOTTOM)
        self._line.setSpacing(COLUMN_GAP)
        self.glyph = glyph
        self._line.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        self._line.addWidget(content, 1)
        self.meta = QLabel()
        style.scale_font(self.meta, SMALL)
        style.ink(self.meta, style.faint(palette))
        self.meta.setVisible(False)
        self._line.addWidget(self.meta, 0, Qt.AlignmentFlag.AlignTop)

    def set_glyph(self, glyph: QWidget) -> None:
        self._line.replaceWidget(self.glyph, glyph)
        self.glyph.hide()
        self.glyph.deleteLater()
        self.glyph = glyph

    def set_meta(self, text: str) -> None:
        self.meta.setText(text)
        self.meta.setVisible(bool(text))

    def connect_down(self) -> None:
        self.connected = True
        self.update()

    def paintEvent(self, _event: Any) -> None:
        if not self.connected:
            return
        painter = QPainter(self)
        painter.setPen(QPen(style.hairline(self._palette), 1))
        painter.drawLine(QPointF(LINE_X, LINE_TOP), QPointF(LINE_X, self.height() - 1))
        painter.end()


class StepRow(TraceRow):
    """One call: the wording muted, its own values bright, a skill tag for knowledge, what it found under it."""

    def __init__(self, text: str, palette: Any, parent: QWidget | None = None):
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 1, 0, 0)
        column.setSpacing(1)
        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setText(step_markup(text, palette))
        self._label.setWordWrap(True)
        column.addWidget(self._label)
        self.note = controls.small("", palette)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        style.ink(self.note, style.faint(palette))
        self.note.setVisible(False)
        column.addWidget(self.note)
        super().__init__(PulseRing(palette), content, palette, parent)
        self.skill = str(getattr(text, "skill", "") or "")
        self.state = PENDING
        self.started = time.monotonic()

    def finish(self, marker: str, note: str = "") -> None:
        """Settle the row: its glyph replaces the pulse, the note says what it found or why it failed."""
        self.state = marker
        failed = marker in (FAILED, REJECTED)
        if isinstance(self.glyph, PulseRing):
            self.glyph.stop()
        self.set_glyph(skill_glyph(self.skill, self._palette, failed))
        took = time.monotonic() - self.started
        self.set_meta(format_seconds(took) if took >= SHORTEST_SHOWN and marker != REJECTED else "")
        if failed and note:
            self.note.setStyleSheet(f"color: {style.css_color(style.danger(self._palette))};")
        self.note.setText(note)
        self.note.setVisible(bool(note))


class ActivityGroup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Taken before the style sheet: "background: transparent" turns the widget's own palette
        # base transparent, which the theme reads as dark and paints the rows in near-white text.
        palette = self._palette = self.palette()
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, GROUP_BOTTOM)
        column.setSpacing(HEADER_GAP)
        self._header = TraceHeader(palette)
        self._header.toggled.connect(self._on_toggled)
        column.addWidget(self._header)
        self._rows_holder = QWidget()
        self._rows = QVBoxLayout(self._rows_holder)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)
        column.addWidget(self._rows_holder)
        self.items: list[TraceRow] = []
        # Off in Personalisation: steps stay folded under the header while the agent works too.
        self._show_steps = personal.load().show_steps
        self._started = 0.0
        self._finished = 0.0
        self._pending = 0
        self._failures = 0
        self._thoughts = 0
        self._closed = False
        self._rows_holder.setVisible(False)
        self._refresh()

    @property
    def expanded(self) -> bool:
        return self._header.expanded

    def add_step(self, text: str) -> StepRow:
        row = StepRow(text, self._palette)
        self._add(row)
        self._pending += 1
        self._refresh()
        return row

    def add_widget(self, widget: QWidget) -> None:
        """A reasoning block, on the timeline with the three-dot glyph."""
        self._thoughts += 1
        self._add(TraceRow(ThinkingDots(self._palette), widget, self._palette))
        self._refresh()

    @property
    def only_thoughts(self) -> bool:
        """Reasoning and nothing else: no header, the row stays shown — the block folds by itself, and a
        reasoning-only turn folded under "Activity · 1 step" would hide the only thing it did."""
        return bool(self.items) and self._thoughts == len(self.items)

    def add_choice(self, answer: str) -> None:
        """The answer the user picked on a question card, as "You chose …" with the person glyph."""
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setText(_spans([(CHOSE + " ", False), (answer, True)], self._palette))
        self._add(TraceRow(skill_glyph(CHOICE, self._palette), label, self._palette))
        self._refresh()

    def reveal(self) -> None:
        self._header.set_expanded(True)

    def fold(self) -> None:
        self._header.set_expanded(False)

    def rest(self) -> None:
        """The turn moved on: the trace folds to its header with the time the steps took."""
        self._closed = True
        self.fold()
        self._refresh()

    def mark_step(self, row: StepRow, ok: bool, note: str = "") -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.finish(DONE if ok else FAILED, note)
        if not ok:
            self._failures += 1
        self._finished = time.monotonic()
        self._refresh()

    def mark_rejected(self, row: StepRow) -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.finish(REJECTED)
        self._refresh()

    def _add(self, row: TraceRow) -> None:
        if self.items:
            self.items[-1].connect_down()
        else:
            self._started = time.monotonic()
            if self._show_steps:
                self.reveal()
        self.items.append(row)
        self._rows.addWidget(row)

    def _refresh(self) -> None:
        count = len(self.items)
        self._header.setVisible(bool(count) and not self.only_thoughts)
        self._rows_holder.setVisible(self._header.expanded or self.only_thoughts)
        working = self._pending and not self._closed
        title = WORKING.format(count) if working else tr_n("Activity · %n step(s)", count)
        self._header.title.setText(title)
        if self._finished and not working:
            self._header.time.setText(format_seconds(self._finished - self._started))
        self._header.status.setVisible(bool(self._failures))
        if self._failures:
            self._header.status.setText("· " + tr_n("%n failed", self._failures))
            style.ink(self._header.status, style.danger(self._palette))

    def _on_toggled(self, expanded: bool) -> None:
        self._rows_holder.setVisible(expanded or self.only_thoughts)


def skill_glyph(skill: str, palette: Any, failed: bool = False) -> QLabel:
    """A step's glyph: its skill's icon in the faint ink (the danger colour when it failed)."""
    label = QLabel()
    label.setFixedSize(GLYPH_BOX, GLYPH_BOX)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    role = GLYPH_ROLES.get(skill, skill)
    colour = style.danger(palette) if failed else style.faint(palette)
    icon = icons.drawn(role, colour, GLYPH) if role in icons.NAMES else None
    if icon is not None:
        label.setPixmap(icon.pixmap(GLYPH, GLYPH))
    return label


def step_markup(text: str, palette: Any) -> str:
    """Rich text for a call: the wording muted, the call's own values bright, a tag for a skill.

    Every span is escaped: the values come from the model, and a layer named
    `<img src=…>` must read as its name, not render.
    """
    parts = list(getattr(text, "parts", ())) or [(str(text), False)]
    last, marked = parts[-1]
    if not marked:
        parts[-1] = (_without_period(last), False)
    markup = _spans(_unquoted(parts), palette)
    if getattr(text, "skill", "") == KNOWLEDGE:
        border = style.css_color(style.hairline(palette))
        markup += (
            f' <span style="color: {style.css_color(style.muted(palette))}; border: 1px solid {border};'
            f' border-radius: {TAG_RADIUS}px; padding: {TAG_PADDING};">&nbsp;{escape(SKILL_TAG)}&nbsp;</span>'
        )
    return markup


def _spans(parts: list[tuple[str, bool]], palette: Any) -> str:
    muted = style.css_color(style.muted(palette))
    bright = style.css_color(style.text(palette))
    return "".join(
        f'<span style="color: {bright}; font-weight: 500;">{escape(span, quote=False)}</span>'
        if marked
        else f'<span style="color: {muted};">{escape(span, quote=False)}</span>'
        for span, marked in parts
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
