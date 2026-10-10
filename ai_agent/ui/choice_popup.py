"""A small popup of exclusive choices: the mode menu, after the design handoff.

A caption, then one row per choice — its name (with an optional badge), a muted
line saying what it does, and its number key — and an optional footer under a
hairline. The current choice is the lit row, no check: the light follows the
pointer and the arrows, and comes back to the current one when the pointer
leaves. The popup is as wide as its text, never wider than its anchor. Digits,
arrows and Enter choose; Esc or a click outside closes. Rows paint their light,
so nothing restyles while a mouse event runs.
"""

from dataclasses import dataclass
from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.ui import controls, style

POPUP_RADIUS = 8
POPUP_PADDING = 4
ROW_RADIUS = 5
ROW_MARGINS = (10, 5, 10, 5)
FOOTER_MARGINS = (10, 2, 10, 4)
PILL_RADIUS = 6
NOTE_SCALE = 12 / 13
NUMBER_SCALE = 11 / 13
NUMBER_KEYS = {getattr(Qt.Key, f"Key_{digit}"): digit - 1 for digit in range(1, 10)}


@dataclass(frozen=True)
class Choice:
    key: str
    title: str
    note: str
    badge: str = ""


class ChoiceRow(controls.RoundedFrame):
    clicked = pyqtSignal(str)
    hovered = pyqtSignal(str)

    def __init__(self, choice: Choice, number: int, palette: Any, parent: QWidget | None = None, wrap: bool = False):
        super().__init__(ROW_RADIUS, parent)
        self.key = choice.key
        self.lit = False
        self._fill = style.card(palette).name()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(*ROW_MARGINS)
        line.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(choice.title)
        style.ink(title, style.text(palette))
        head.addWidget(title)
        if choice.badge:
            head.addWidget(_pill(choice.badge, palette), 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        text.addLayout(head)
        self.note = QLabel(choice.note)
        style.scale_font(self.note, NOTE_SCALE)
        style.ink(self.note, style.faint(palette))
        # In the feed the row must shrink with the dock, so there it wraps; the popup wraps
        # only when its anchor is narrower than the longest note.
        self.note.setWordWrap(wrap)
        text.addWidget(self.note)
        line.addLayout(text, 1)
        self.number = QLabel(str(number))
        style.scale_font(self.number, NUMBER_SCALE)
        style.ink(self.number, style.faint(palette))
        line.addWidget(self.number, 0, Qt.AlignmentFlag.AlignTop)

    def set_highlighted(self, highlighted: bool) -> None:
        self.lit = highlighted
        self.set_look(self._fill if highlighted else None, None)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)

    def enterEvent(self, event: Any) -> None:
        self.hovered.emit(self.key)
        super().enterEvent(event)


class ChoicePopup(controls.RoundedFrame):
    chosen = pyqtSignal(str)

    def __init__(
        self, caption: str, choices: list[Choice], palette: Any, footer: str = "", parent: QWidget | None = None
    ):
        super().__init__(POPUP_RADIUS, parent)
        self._choices = choices
        self._index = 0
        self._current = 0
        try:
            flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        except TypeError:
            flags = None
        if flags is not None:
            self.setWindowFlags(flags)
        # A popup is a window of its own: it does not inherit the panel's palette, so it takes the theme's.
        style.apply_palette(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.set_look(style.surface(palette).name(), style.border_strong(palette).name())
        column = QVBoxLayout(self)
        column.setContentsMargins(POPUP_PADDING, POPUP_PADDING, POPUP_PADDING, POPUP_PADDING)
        column.setSpacing(1)
        column.addWidget(controls.caption(caption, palette))
        self.rows: list[ChoiceRow] = []
        for number, choice in enumerate(choices, 1):
            row = ChoiceRow(choice, number, palette)
            row.clicked.connect(self.choose)
            row.hovered.connect(lambda key: self._highlight(self._position(key)))
            self.rows.append(row)
            column.addWidget(row)
        if footer:
            column.addWidget(controls.menu_rule(palette))
            hint = QLabel(footer)
            style.scale_font(hint, NOTE_SCALE)
            style.ink(hint, style.faint(palette))
            hint.setContentsMargins(*FOOTER_MARGINS)
            column.addWidget(hint)

    def open_above(self, anchor: QWidget, current: str) -> None:
        """Show the popup over `anchor`, left edges aligned, as wide as its text allows, `current` lit."""
        self._current = self._position(current)
        self._highlight(self._current)
        for row in self.rows:
            row.note.setWordWrap(False)
        natural = self.sizeHint().width()
        narrow = natural > anchor.width() > 0
        for row in self.rows:
            row.note.setWordWrap(narrow)
        self.setFixedWidth(anchor.width() if narrow else natural)
        self.adjustSize()
        corner = anchor.mapToGlobal(QPoint(0, 0))
        self.move(corner.x(), corner.y() - self.sizeHint().height() - controls.MENU_GAP)
        self.show()
        self.setFocus()

    def choose(self, key: str) -> None:
        self.hide()
        self.chosen.emit(key)

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if key in NUMBER_KEYS and NUMBER_KEYS[key] < len(self._choices):
            self.choose(self._choices[NUMBER_KEYS[key]].key)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = -1 if key == Qt.Key.Key_Up else 1
            self._highlight((self._index + step) % len(self._choices))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.choose(self._choices[self._index].key)
        elif key == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event: Any) -> None:
        # The light is the only mark of the current choice: it goes back there once the pointer leaves.
        self._highlight(self._current)
        super().leaveEvent(event)

    def _position(self, key: str) -> int:
        return next((index for index, choice in enumerate(self._choices) if choice.key == key), 0)

    def _highlight(self, index: int) -> None:
        self._index = index
        for position, row in enumerate(self.rows):
            row.set_highlighted(position == index)


def _pill(text: str, palette: Any) -> QLabel:
    """A quiet tag that stays visible on a highlighted row, whose fill is the card colour."""
    pill = QLabel(text)
    style.scale_font(pill, controls.SMALL_SCALE)
    pill.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.hairline(palette))};"
        f"color: {style.css_color(style.muted(palette))}; border-radius: {PILL_RADIUS}px; padding: 1px 6px; }}"
    )
    return pill
