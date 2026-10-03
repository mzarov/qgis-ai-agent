"""A small popup of exclusive choices, laid out like Claude Code's mode menu.

A caption, then one row per choice: its name (with an optional badge), a muted
line saying what it does, a check on the current one and its number key on the
right. Digits, arrows and Enter choose; Esc or a click outside closes. Rows
paint their hover and highlight, so nothing restyles while a mouse event runs.
"""

from dataclasses import dataclass
from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.ui import controls, style

POPUP_RADIUS = 12
ROW_RADIUS = 8
POPUP_WIDTH = 360
CHECK = "✓"
PILL_RADIUS = 6
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

    def __init__(self, choice: Choice, number: int, palette: Any, parent: QWidget | None = None):
        super().__init__(ROW_RADIUS, parent)
        self.key = choice.key
        self._fill = style.card(palette).name()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 8, 10, 8)
        line.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(choice.title)
        title.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        head.addWidget(title)
        if choice.badge:
            head.addWidget(_pill(choice.badge, palette), 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        text.addLayout(head)
        note = controls.small(choice.note, palette)
        # One line each: a wrapping label asks for height it never uses, and the caption got it.
        note.setWordWrap(False)
        text.addWidget(note)
        line.addLayout(text, 1)
        self.check = QLabel(CHECK)
        self.check.setStyleSheet(f"color: {style.css_color(style.accent(palette))};")
        line.addWidget(self.check, 0, Qt.AlignmentFlag.AlignVCenter)
        number_label = QLabel(str(number))
        number_label.setStyleSheet(f"color: {style.css_color(style.faint(palette))};")
        line.addWidget(number_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_highlighted(self, highlighted: bool) -> None:
        self.set_look(self._fill if highlighted else None, None)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)

    def enterEvent(self, event: Any) -> None:
        self.hovered.emit(self.key)
        super().enterEvent(event)


class ChoicePopup(controls.RoundedFrame):
    chosen = pyqtSignal(str)

    def __init__(self, caption: str, choices: list[Choice], palette: Any, parent: QWidget | None = None):
        super().__init__(POPUP_RADIUS, parent)
        self._choices = choices
        self._index = 0
        try:
            flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        except TypeError:
            flags = None
        if flags is not None:
            self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        self.setFixedWidth(POPUP_WIDTH)
        column = QVBoxLayout(self)
        column.setContentsMargins(6, 12, 6, 6)
        column.setSpacing(2)
        heading = controls.small(caption, palette)
        heading.setWordWrap(False)
        heading.setContentsMargins(10, 0, 0, 6)
        column.addWidget(heading)
        self.rows: list[ChoiceRow] = []
        for number, choice in enumerate(choices, 1):
            row = ChoiceRow(choice, number, palette)
            row.clicked.connect(self.choose)
            row.hovered.connect(lambda key: self._highlight(self._position(key)))
            self.rows.append(row)
            column.addWidget(row)

    def open_above(self, anchor: QWidget, current: str) -> None:
        """Show the popup over `anchor`, its left edges aligned, with `current` checked and lit."""
        for row in self.rows:
            row.check.setVisible(row.key == current)
        self._highlight(self._position(current))
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
