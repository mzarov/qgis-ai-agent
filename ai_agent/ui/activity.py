"""One turn's tool calls and reasoning, listed the way TerraLab lists them.

The header names the first calls and how long the turn took, "Reading layer
roads, Adding basemap +2 · 9.4 s". The rows sit open in a hairline list, one per
call with its skill's icon and, under it, what the call found; the reasoning is
a row of its own. The list stays open after the answer and folds when the next
request starts. Success is the quiet default and carries no mark; only a failed
or rejected call does.
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
STEP_FONT_SCALE = 0.95
LIST_INDENT = 2
ROW_PAD = 5
HEADER_GAP = 6
ICON = 14
ICON_GAP = 8
NOTE_GAP = 2
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
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(HEADER_GAP)
        self._header = Disclosure(palette)
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
        self._steps_holder.add_row(widget)
        self._extras += 1
        self._refresh()

    def reveal(self) -> None:
        self._toggle.setChecked(True)
        self._steps_holder.setVisible(True)

    def rest(self) -> None:
        """The turn moved on: the list stays open with the time it took, until the next request folds it."""
        self._closed = True
        if not self._count:
            # A reasoning-only turn has no header to reopen it from: its row stays.
            self._steps_holder.setVisible(self._extras > 0)
        elif self._finished:
            self._header.set_detail(format_seconds(self._finished - self._started))
        self._refresh()

    def fold(self) -> None:
        """Collapse to the header line; an earlier turn makes room for the next one."""
        if self._count:
            self._toggle.setChecked(False)

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
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(NOTE_GAP)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(ICON_GAP)
        column.addLayout(row)
        self.icon = QLabel()
        self.icon.setFixedSize(ICON, ICON)
        skill = str(getattr(text, "skill", "") or "")
        glyph = icons.drawn(skill, style.muted(palette), ICON) if skill in icons.NAMES else None
        if glyph is not None:
            self.icon.setPixmap(glyph.pixmap(ICON, ICON))
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)

        self.state = PENDING
        self._label = QLabel()
        markup = step_markup(text, palette)
        self._label.setTextFormat(Qt.TextFormat.PlainText if markup is None else Qt.TextFormat.RichText)
        self._label.setText(_without_period(str(text)) if markup is None else markup)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        style.scale_font(self._label, STEP_FONT_SCALE)
        row.addWidget(self._label, 1)

        self._marker = QLabel()
        self._marker.setFont(self._label.font())
        self._marker.setVisible(False)
        row.addWidget(self._marker, 0, Qt.AlignmentFlag.AlignTop)

        self.note = controls.small("", palette)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setContentsMargins(ICON + ICON_GAP, 0, 0, 0)
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
