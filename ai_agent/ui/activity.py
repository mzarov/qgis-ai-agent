"""One turn's tool calls and reasoning as the design's "work trace": a quiet timeline above the answer.

Not a card. The header is the timeline's first node: a chevron in the glyph
column, "Activity · 5 steps" (while working "Working · step 3") level with the
steps' text, the time on the right; a click anywhere on it folds the list, the
chevron turning and the list closing smoothly. Each step is a row: a 16 px glyph
in the faint ink, the call's wording muted and its own values bright, a skill
tag for a loaded skill, a second line saying what it found, the step's time on
the right. One hairline joins the nodes, broken around each glyph by the same
small gap, so the list reads as one timeline. The running step pulses a small
accent ring instead of its glyph. Reasoning and the user's choice on a question
card are rows of their own. Success carries no mark; a failed step shows its
reason in the danger colour. A reopened conversation rebuilds the same rows from
what was saved, folded and without animation.
"""

import time
from html import escape
from typing import Any

from qgis.PyQt.QtCore import QPoint, QPointF, QRect, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QPainter, QPen
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.config import personal
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, folding, icons, style
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
ROW_BOTTOM = 8
HEADER_GAP = 6
# With the feed's spacing, the handoff's 14 px from the trace to whatever follows it.
GROUP_BOTTOM = 3
# The hairline stops this far from every glyph, whatever the glyph's size.
LINE_GAP = 3
SMALL = 0.92
CHEVRON = 12
TAG_SCALE = 11 / 13
TAG_RADIUS = 4
PULSE = 9
PULSE_PEN = 1.5
PULSE_MS = 1200
PULSE_LOW = 0.35
# A step faster than this shows no time: "0.0 s" claims a measurement that says nothing.
SHORTEST_SHOWN = 0.05
# Where an icon glyph's drawing sits in its box, top to bottom; smaller glyphs say their own.
ICON_MARK = ((GLYPH_BOX - GLYPH) / 2, (GLYPH_BOX + GLYPH) / 2)


class RecordedText(str):
    """A saved step's wording, with the marked values and the skill a live CallSummary carries."""

    parts: tuple[tuple[str, bool], ...] = ()
    skill = ""


def recorded_text(step: dict[str, Any]) -> RecordedText:
    text = RecordedText(str(step.get("text") or ""))
    text.parts = tuple((str(part[0]), bool(part[1])) for part in step.get("parts") or () if len(part) == 2)
    text.skill = str(step.get("skill") or "")
    return text


class TraceHeader(QWidget):
    """The fold line: a turning chevron in the glyph column, the title level with the steps, the time."""

    toggled = pyqtSignal(bool)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.expanded = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(COLUMN_GAP)
        self.chevron = folding.Chevron(palette, CHEVRON, GLYPH_BOX)
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

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if expanded != self.expanded:
            self.expanded = expanded
            self.chevron.set_open(expanded, animate)
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


class PulseRing(QWidget):
    """The running step's mark: a small accent ring whose opacity breathes."""

    mark = ((GLYPH_BOX - PULSE) / 2, (GLYPH_BOX + PULSE) / 2)

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

    mark = (GLYPH_BOX / 2 - 1.5, GLYPH_BOX / 2 + 1.5)

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
    """A row on the timeline: glyph, content, time. The group draws the hairline between the glyphs."""

    def __init__(self, glyph: QWidget, content: QWidget, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
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

    def set_bottom(self, margin: int) -> None:
        self._line.setContentsMargins(0, 0, 0, margin)


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
        self.skill = str(getattr(text, "skill", "") or "")
        self.tag: QLabel | None = None
        if self.skill == KNOWLEDGE:
            # A real chip beside the words: rich text in a label draws no border round a span.
            head = QHBoxLayout()
            head.setSpacing(6)
            head.addWidget(self._label)
            self.tag = _tag(SKILL_TAG, palette)
            head.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
            head.addStretch(1)
            column.addLayout(head)
        else:
            self._label.setWordWrap(True)
            column.addWidget(self._label)
        self.note = controls.small("", palette)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        style.ink(self.note, style.faint(palette))
        self.note.setVisible(False)
        column.addWidget(self.note)
        super().__init__(PulseRing(palette), content, palette, parent)
        self.state = PENDING
        self.started = time.monotonic()

    def finish(self, marker: str, note: str = "", seconds: float | None = None) -> None:
        """Settle the row: its glyph replaces the pulse, the note says what it found or why it failed.

        `seconds` is a saved step's time; a live one measures its own.
        """
        self.state = marker
        failed = marker in (FAILED, REJECTED)
        if isinstance(self.glyph, PulseRing):
            self.glyph.stop()
        self.set_glyph(skill_glyph(self.skill, self._palette, failed))
        took = time.monotonic() - self.started if seconds is None else seconds
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
        # No spacing here: the gap under the header belongs to the folding list, so it opens with it.
        column.setSpacing(0)
        self._header = TraceHeader(palette)
        self._header.toggled.connect(self._on_toggled)
        column.addWidget(self._header)
        rows = QWidget()
        self._rows = QVBoxLayout(rows)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)
        # The fold shows a part of the rows, never squeezes them: they keep their height and are clipped.
        self._rows_holder = folding.ClipBox(rows, self.update)
        column.addWidget(self._rows_holder)
        self.items: list[TraceRow] = []
        # Off in Personalisation: steps stay folded under the header while the agent works too.
        self._show_steps = personal.load().show_steps
        # A replayed group is built folded at once: no animation, no live clock.
        self.quiet = False
        self._recorded: float | None = None
        self._started = 0.0
        self._finished = 0.0
        self._pending = 0
        self._failures = 0
        self._thoughts = 0
        self._closed = False
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

    def add_recorded_step(self, step: dict[str, Any]) -> None:
        """A saved call, settled as it ended; a call the run never finished reads as done."""
        row = self.add_step(recorded_text(step))
        if step.get("rejected"):
            self.mark_rejected(row)
            return
        ok = step.get("ok")
        seconds = step.get("seconds")
        self.mark_step(
            row, ok is not False, str(step.get("note") or ""), seconds if isinstance(seconds, (int, float)) else 0.0
        )

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
        self._header.set_expanded(True, not self.quiet)

    def fold(self) -> None:
        self._header.set_expanded(False, not self.quiet)

    def rest(self) -> None:
        """The turn moved on: the trace folds to its header with the time the steps took."""
        self._closed = True
        self.fold()
        self._refresh()

    def settle(self, seconds: Any = None) -> None:
        """A replayed turn: folded at once, its header showing the time the record kept."""
        self._recorded = float(seconds) if isinstance(seconds, (int, float)) else None
        self.rest()
        self.finish_folding()
        # Built still; from now on the user's clicks open and close it like any other.
        self.quiet = False

    def mark_step(self, row: StepRow, ok: bool, note: str = "", seconds: float | None = None) -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.finish(DONE if ok else FAILED, note, seconds)
        if not ok:
            self._failures += 1
        self._finished = time.monotonic()
        self._refresh()

    def mark_rejected(self, row: StepRow) -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.finish(REJECTED)
        self._refresh()

    def finish_folding(self) -> None:
        """End any fold or turn at once, as a screenshot wants it."""
        self._rows_holder.finish()
        self._header.chevron.finish()

    def _add(self, row: TraceRow) -> None:
        if not self.items:
            self._started = time.monotonic()
            if self._show_steps:
                self.reveal()
        self.items.append(row)
        self._rows.addWidget(row)
        self.update()

    def _refresh(self) -> None:
        count = len(self.items)
        self._header.setVisible(bool(count) and not self.only_thoughts)
        self._rows.setContentsMargins(0, 0 if self.only_thoughts else HEADER_GAP, 0, 0)
        # Reasoning alone stands in for the header: no row gap under it, the answer sits as close
        # below it as below a folded "Activity" line.
        for row in self.items:
            row.set_bottom(0 if self.only_thoughts and row is self.items[-1] else ROW_BOTTOM)
        if self.only_thoughts and self._rows_holder.isHidden():
            self._rows_holder.set_open(True, animate=False)
        working = self._pending and not self._closed
        title = WORKING.format(count) if working else tr_n("Activity · %n step(s)", count)
        self._header.title.setText(title)
        if self._recorded is not None:
            self._header.time.setText(format_seconds(self._recorded) if self._recorded >= SHORTEST_SHOWN else "")
        elif self._finished and not working:
            self._header.time.setText(format_seconds(self._finished - self._started))
        self._header.status.setVisible(bool(self._failures))
        if self._failures:
            self._header.status.setText("· " + tr_n("%n failed", self._failures))
            style.ink(self._header.status, style.danger(self._palette))
        self.update()

    def _on_toggled(self, expanded: bool) -> None:
        self._rows_holder.set_open(expanded or self.only_thoughts, animate=not self.quiet)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        nodes = self._nodes()
        if len(nodes) < 2:
            return
        painter = QPainter(self)
        painter.setPen(QPen(style.hairline(self._palette), 1))
        # While the list folds, only what is still shown of it carries the line.
        holder = self._rows_holder.geometry()
        painter.setClipRect(QRect(0, 0, self.width(), holder.y() + holder.height()))
        for (x, _top, upper), (_x, lower, _bottom) in zip(nodes, nodes[1:], strict=False):
            if lower - upper > 2 * LINE_GAP:
                painter.drawLine(QPointF(x, upper + LINE_GAP), QPointF(x, lower - LINE_GAP))
        painter.end()

    def _nodes(self) -> list[tuple[float, float, float]]:
        """Each node's line axis, the top and the bottom of its drawing, in the group's coordinates."""
        if self._rows_holder.isHidden():
            return []
        glyphs: list[QWidget] = [row.glyph for row in self.items]
        if not self._header.isHidden():
            glyphs.insert(0, self._header.chevron)
        nodes = []
        for glyph in glyphs:
            origin = glyph.mapTo(self, QPoint(0, 0))
            top, bottom = getattr(glyph, "mark", ICON_MARK)
            nodes.append((origin.x() + glyph.width() / 2 - 0.5, origin.y() + top, origin.y() + bottom))
        return nodes


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
    """Rich text for a call: the wording muted, the call's own values bright.

    Every span is escaped: the values come from the model, and a layer named
    `<img src=…>` must read as its name, not render.
    """
    parts = list(getattr(text, "parts", ())) or [(str(text), False)]
    last, marked = parts[-1]
    if not marked:
        parts[-1] = (_without_period(last), False)
    return _spans(_unquoted(parts), palette)


def _tag(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    style.scale_font(label, TAG_SCALE)
    label.setStyleSheet(
        f"QLabel {{ color: {style.css_color(style.muted(palette))};"
        f" border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f" border-radius: {TAG_RADIUS}px; padding: 0 5px; }}"
    )
    return label


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
