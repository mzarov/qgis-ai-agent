"""One turn's tool calls and reasoning, listed the way TerraLab lists them.

The header names the first calls and how long the turn took, "Reading layer
roads, Adding basemap +2 · 9.4 s". While the agent works the rows sit open, one
per call: a coloured badge with its skill's icon, the wording muted with the
call's own values bright, and under it what the call found; the reasoning is a
row of its own. When the answer arrives the list folds to its header line. Success
is the quiet default and carries no mark; only a failed or rejected call does.
"""

import time
from html import escape
from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr_n
from ai_agent.ui import controls, icons, style
from ai_agent.ui.disclosure import Disclosure
from ai_agent.ui.durations import format_seconds

PENDING = "●"
DONE = ""
FAILED = "✕"
REJECTED = "⊘"
RECOVERED = "↺"
NOTE = "· {0}"
CLOSING = {"'": "'", '"': '"', "«": "»", "“": "”"}
LIST_INDENT = 2
ROW_PAD = 5
HEADER_GAP = 8
GROUP_BOTTOM = 8
LEAD = 14
BADGE = 24
BADGE_RADIUS = 7
GLYPH = 14
# The badge's wash: enough of the skill's hue to tell rows apart, little enough to stay quiet.
BADGE_WASH = 0.16
BADGE_GAP = 10
# One text line sits level with the middle of the badge.
TEXT_TOP = 3
NOTE_GAP = 1
THINKING = "thinking"
# Each skill keeps one hue from the categorical palette, so a row's kind is readable at a glance.
HUES = {
    "inspect": 0,
    "web": 0,
    "fields": 0,
    "data": 1,
    "python": 1,
    "plugins": 1,
    "project": 2,
    "tables": 2,
    "draw": 3,
    "edit": 3,
    "annotations": 3,
    "style": 4,
    "charts": 4,
    "osm": 5,
    "processing": 6,
    "layout": 6,
    "three_d": 6,
    "knowledge": 6,
    THINKING: 6,
}
NAMED_CALLS = 2
# "+2" reads the same in every language, so it is no translation string.
MORE = "{0} +{1}"


class ActivityList(QWidget):
    """The rows of a group, open on the page without a frame: a box around every turn read as a wall of cards."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.items: list[QWidget] = []
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(LIST_INDENT, 0, 0, 0)
        self.rows.setSpacing(0)

    def add_row(self, widget: QWidget) -> None:
        widget.setContentsMargins(0, ROW_PAD, 0, ROW_PAD)
        self.items.append(widget)
        self.rows.addWidget(widget)


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
        self._header = Disclosure(palette)
        lead = icons.drawn("sparkles", style.accent(palette), LEAD)
        if lead is not None:
            mark = QLabel()
            mark.setPixmap(lead.pixmap(LEAD, LEAD))
            self._header.add_lead(mark)
        self._toggle = self._header.toggle
        self._title = self._header.title
        self._status = QLabel()
        self._header.add_note(self._status)
        self._header.toggled.connect(self._on_toggled)
        column.addWidget(self._header)
        self._names: list[str] = []
        self._started = 0.0
        self._finished = 0.0
        self._steps_holder = ActivityList()
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
        row = StepRow(text, self._palette)
        self._steps_holder.add_row(row)
        if not self._count:
            self._started = time.monotonic()
            self.reveal()
        self._names.append(_without_period(str(text)))
        self._count += 1
        self._pending += 1
        self._refresh()
        return row

    def add_widget(self, widget: QWidget) -> None:
        """A reasoning block, as a row with its own badge so it lines up with the calls."""
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(BADGE_GAP)
        line.addWidget(badge(THINKING, self._palette), 0, Qt.AlignmentFlag.AlignTop)
        widget.setContentsMargins(0, TEXT_TOP, 0, 0)
        line.addWidget(widget, 1)
        self._steps_holder.add_row(holder)
        self._extras += 1
        self._refresh()

    def reveal(self) -> None:
        self._toggle.setChecked(True)
        self._steps_holder.setVisible(True)

    def rest(self) -> None:
        """The turn moved on: the list folds to its header line, with the time the calls took."""
        self._closed = True
        if not self._count:
            # A reasoning-only turn has no header to reopen it from: its row stays.
            self._steps_holder.setVisible(self._extras > 0)
        else:
            self._toggle.setChecked(False)
            if self._finished:
                self._header.set_detail(format_seconds(self._finished - self._started))
        self._refresh()

    def mark_step(self, row: "StepRow", ok: bool, note: str = "") -> None:
        self._settle(row, DONE if ok else FAILED)
        if not ok:
            self._failures += 1
        elif note:
            row.set_note(note)
        self._finished = time.monotonic()
        self._refresh()

    def mark_rejected(self, row: "StepRow") -> None:
        self._settle(row, REJECTED)
        self._rejected = True
        self._refresh()

    def _settle(self, row: "StepRow", state: str) -> None:
        if row.state == PENDING:
            self._pending = max(0, self._pending - 1)
        row.set_state(state)

    def _refresh(self) -> None:
        palette = self._palette
        self._header.setVisible(bool(self._count))
        title = ", ".join(self._names[:NAMED_CALLS])
        if len(self._names) > NAMED_CALLS:
            title = MORE.format(title, len(self._names) - NAMED_CALLS)
        self._title.setText(title)
        self._title.setToolTip("\n".join(self._names))
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
        style.ink(self._status, colour)

    def _on_toggled(self, expanded: bool) -> None:
        if self._count:
            self._steps_holder.setVisible(expanded)


class StepRow(QWidget):
    """One call: its skill's icon, the wording muted with its own values bright, a mark only when it
    did not succeed, and under it what the call found."""

    def __init__(self, text: str, palette, parent=None):
        super().__init__(parent)
        self.setStyleSheet("border: none;")
        self._palette = palette
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(BADGE_GAP)
        self.icon = badge(str(getattr(text, "skill", "") or ""), palette)
        line.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setContentsMargins(0, TEXT_TOP, 0, 0)
        column.setSpacing(NOTE_GAP)
        line.addLayout(column, 1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(BADGE_GAP)
        column.addLayout(row)

        self.state = PENDING
        self._label = QLabel()
        markup = step_markup(text, palette)
        self._label.setTextFormat(Qt.TextFormat.PlainText if markup is None else Qt.TextFormat.RichText)
        self._label.setText(_without_period(str(text)) if markup is None else markup)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        row.addWidget(self._label, 1)

        self._marker = QLabel()
        self._marker.setFont(self._label.font())
        self._marker.setVisible(False)
        row.addWidget(self._marker, 0, Qt.AlignmentFlag.AlignTop)

        self.note = controls.small("", palette)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setVisible(False)
        column.addWidget(self.note)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_state(self, marker: str) -> None:
        self.state = marker
        self._marker.setText(marker)
        self._marker.setVisible(bool(marker))
        colour = style.warning(self._palette) if marker == REJECTED else style.danger(self._palette)
        self._marker.setStyleSheet(f"color: {style.css_color(colour)};")


def badge(skill: str, palette: Any) -> QLabel:
    """The skill's icon in its hue on a pale wash of that hue; a neutral blank tile for an unknown kind."""
    label = QLabel()
    label.setFixedSize(BADGE, BADGE)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hue = style.series(palette, HUES[skill]) if skill in HUES else style.muted(palette)
    wash = style.blend(style.background(palette), hue, BADGE_WASH)
    label.setStyleSheet(f"QLabel {{ background: {style.css_color(wash)}; border-radius: {BADGE_RADIUS}px; }}")
    role = "brain" if skill == THINKING else skill
    glyph = icons.drawn(role, hue, GLYPH) if role in icons.NAMES else None
    if glyph is not None:
        label.setPixmap(glyph.pixmap(GLYPH, GLYPH))
    return label


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
