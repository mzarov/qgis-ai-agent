"""Small custom controls for the settings window and the composer.

`Segmented` and `RadioCards` keep the slice of the `QComboBox` API the dialog
already relies on (`currentText`, `findText`, `setCurrentIndex`, the change
signals), so saving and loading code reads them exactly like the combo boxes
they replace. Everything is drawn from the palette through `style`.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ai_agent.ui import style

SEGMENT_NAME = "segmented"
CARD_NAME = "radioCard"
SEGMENT_RADIUS = 8
SEGMENT_INNER_RADIUS = 6
CHIP_HEIGHT = 26
CHIP_RADIUS = CHIP_HEIGHT // 2
BADGE_RADIUS = 8
KEY_RADIUS = 4
KEY_SCALE = 0.8
KEY_PADDING = 5
KEY_MIN_WIDTH = 18
KEY_EXTRA_HEIGHT = 4
KEY_EDGE_TINT = 0.35
RADIO_SIZE = 16
RADIO_DOT = 8
SMALL_SCALE = 0.85
BADGE_KINDS = ("neutral", "ok", "warn", "accent", "bad")


class Segmented(QFrame):
    """Mutually exclusive choices in one pill; reads like a combo box."""

    currentIndexChanged = pyqtSignal(int)
    currentTextChanged = pyqtSignal(str)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._items: list[str] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._chosen)
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(2, 2, 2, 2)
        self._line.setSpacing(0)
        self.setObjectName(SEGMENT_NAME)
        self.setStyleSheet(
            f"QFrame#{SEGMENT_NAME} {{ background: {style.css_color(style.sunken(palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {SEGMENT_RADIUS}px; }}"
        )

    def addItems(self, items: list[str]) -> None:
        for item in items:
            button = QPushButton(item)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(self._segment_style())
            self._group.addButton(button, len(self._items))
            self._line.addWidget(button)
            self._items.append(item)
        if self._group.checkedId() < 0 and self._items:
            self._group.button(0).setChecked(True)

    def count(self) -> int:
        return len(self._items)

    def itemText(self, index: int) -> str:
        return self._items[index] if 0 <= index < len(self._items) else ""

    def findText(self, text: str) -> int:
        return self._items.index(text) if text in self._items else -1

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentText(self) -> str:
        return self.itemText(self.currentIndex())

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self._items) or index == self.currentIndex():
            return
        self._group.button(index).setChecked(True)
        self._chosen(index)

    def setCurrentText(self, text: str) -> None:
        self.setCurrentIndex(self.findText(text))

    def _chosen(self, index: int) -> None:
        self.currentIndexChanged.emit(index)
        self.currentTextChanged.emit(self.itemText(index))

    def _segment_style(self) -> str:
        return (
            f"QPushButton {{ background: transparent; border: none; border-radius: {SEGMENT_INNER_RADIUS}px;"
            f"padding: 4px 12px; color: {style.css_color(style.muted(self._palette))}; }}"
            f"QPushButton:hover {{ color: {style.css_color(style.text(self._palette))}; }}"
            f"QPushButton:checked {{ background: {style.css_color(style.panel(self._palette))};"
            f"color: {style.css_color(style.text(self._palette))}; font-weight: 600; }}"
        )


class Chips(QWidget):
    """Preset values for a line edit: a click writes the value, typing lights the matching chip."""

    def __init__(
        self,
        palette: Any,
        edit: QLineEdit,
        presets: list[tuple[str, str]],
        parse: Callable[[str], int | None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._palette = palette
        self._edit = edit
        self._parse = parse
        self._chips: list[tuple[QPushButton, int | None]] = []
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        for label, value in presets:
            chip = QPushButton(label)
            chip.setCheckable(True)
            chip.setFixedHeight(CHIP_HEIGHT)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(self._chip_style())
            chip.clicked.connect(lambda _checked=False, text=value: self._edit.setText(text))
            line.addWidget(chip)
            self._chips.append((chip, parse(value)))
        edit.textChanged.connect(self._sync)
        self._sync(edit.text())

    def _sync(self, text: str) -> None:
        value = self._parse(text)
        for chip, preset in self._chips:
            chip.setChecked(value is not None and value == preset)

    def _chip_style(self) -> str:
        accent = style.accent(self._palette)
        return (
            f"QPushButton {{ background: {style.css_color(style.panel(self._palette))};"
            f"color: {style.css_color(style.text(self._palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.border_strong(self._palette))};"
            f"border-radius: {CHIP_RADIUS}px; padding: 0px 11px; }}"
            f"QPushButton:checked {{ background: {style.css_color(style.soft(self._palette, accent))};"
            f"border-color: {style.css_color(accent)}; color: {style.css_color(style.accent_ink(self._palette))};"
            "font-weight: 600; }"
        )


class RadioMark(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.checked = False
        self.setFixedSize(RADIO_SIZE, RADIO_SIZE)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = style.accent(self._palette) if self.checked else style.muted(self._palette)
        pen = QPen(colour)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1, 1, RADIO_SIZE - 2, RADIO_SIZE - 2))
        if self.checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            offset = (RADIO_SIZE - RADIO_DOT) / 2
            painter.drawEllipse(QRectF(offset, offset, RADIO_DOT, RADIO_DOT))
        painter.end()


class RadioCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, palette: Any, title: str, note: str):
        super().__init__()
        self._palette = palette
        self.setObjectName(CARD_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(14, 11, 14, 11)
        line.setSpacing(12)
        self.mark = RadioMark(palette)
        line.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        self._column = QVBoxLayout()
        self._column.setSpacing(2)
        self.title = QLabel(title)
        self._column.addWidget(self.title)
        self.note = small(note, palette)
        self.note.setVisible(bool(note))
        self._column.addWidget(self.note)
        line.addLayout(self._column, 1)
        self.set_checked(False)

    def add_extra(self, widget: QWidget) -> None:
        self._column.addSpacing(6)
        self._column.addWidget(widget)

    def set_checked(self, checked: bool) -> None:
        self.mark.checked = checked
        self.mark.update()
        # The chosen card keeps its fill and gains a two-pixel accent edge, as in the approved mockup;
        # the margin swap keeps every card the same outer size.
        border = style.accent(self._palette) if checked else style.hairline(self._palette)
        width = 2 if checked else style.HAIRLINE
        self.setStyleSheet(
            f"QFrame#{CARD_NAME} {{ background: {style.css_color(style.panel(self._palette))};"
            f"border: {width}px solid {style.css_color(border)}; border-radius: {style.CARD_RADIUS}px;"
            f"margin: {2 - width}px; }}"
        )

    def mousePressEvent(self, _event: Any) -> None:
        self.clicked.emit()


class RadioCards(QWidget):
    """A vertical stack of choice cards; reads like a combo box with item data."""

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._cards: list[RadioCard] = []
        self._data: list[Any] = []
        self._index = -1
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(8)

    def addItem(self, title: str, data: Any = None, note: str = "") -> RadioCard:
        card = RadioCard(self._palette, title, note)
        index = len(self._cards)
        card.clicked.connect(lambda: self.setCurrentIndex(index))
        self._cards.append(card)
        self._data.append(data)
        self._column.addWidget(card)
        if self._index < 0:
            self._select(0)
        return card

    def count(self) -> int:
        return len(self._cards)

    def card(self, index: int) -> RadioCard:
        return self._cards[index]

    def findData(self, data: Any) -> int:
        return self._data.index(data) if data in self._data else -1

    def currentIndex(self) -> int:
        return self._index

    def currentData(self) -> Any:
        return self._data[self._index] if 0 <= self._index < len(self._data) else None

    def currentText(self) -> str:
        return self._cards[self._index].title.text() if 0 <= self._index < len(self._cards) else ""

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self._cards) or index == self._index:
            return
        self._select(index)
        self.currentIndexChanged.emit(index)

    def _select(self, index: int) -> None:
        self._index = index
        for at, card in enumerate(self._cards):
            card.set_checked(at == index)


def small(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * SMALL_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label


def badge(text: str, kind: str, palette: Any) -> QLabel:
    """A small pill: neutral, ok, warn, accent or bad."""
    label = QLabel(text)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * SMALL_SCALE))
    font.setBold(True)
    label.setFont(font)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    paint_badge(label, kind, palette)
    return label


def paint_badge(label: QLabel, kind: str, palette: Any) -> None:
    colours = {
        "ok": style.success(palette),
        "warn": style.warning(palette),
        "accent": style.accent(palette),
        "bad": style.danger(palette),
    }
    colour = colours.get(kind)
    fill = style.soft(palette, colour) if colour is not None else style.card(palette)
    ink = colour if colour is not None else style.muted(palette)
    if kind == "accent":
        ink = style.accent_ink(palette)
    label.setStyleSheet(
        f"QLabel {{ background: {style.css_color(fill)}; color: {style.css_color(ink)};"
        f"border-radius: {BADGE_RADIUS}px; padding: 1px 7px; }}"
    )


class KeyCap(QLabel):
    """A keyboard key drawn by hand: a rounded outline, a slightly heavier bottom edge, the glyph centred.

    Style sheets cannot do this reliably: a thicker bottom border shifts the text off centre, and a
    hairline border all but disappears on a dark palette.
    """

    def __init__(self, text: str, palette: Any, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._palette = palette
        font = self.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * KEY_SCALE))
        self.setFont(font)
        metrics = self.fontMetrics()
        self.setFixedSize(
            max(KEY_MIN_WIDTH, metrics.horizontalAdvance(text) + 2 * KEY_PADDING), metrics.height() + KEY_EXTRA_HEIGHT
        )

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        edge = style.blend(style.muted(self._palette), style.surface(self._palette), KEY_EDGE_TINT)
        body = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge)
        painter.drawRoundedRect(body.translated(0, 1.0), KEY_RADIUS, KEY_RADIUS)
        painter.setBrush(style.panel(self._palette))
        pen = QPen(edge)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(body, KEY_RADIUS, KEY_RADIUS)
        painter.setPen(style.muted(self._palette))
        painter.drawText(body, int(Qt.AlignmentFlag.AlignCenter), self.text())
        painter.end()


def keycap(text: str, palette: Any) -> QLabel:
    """A keyboard key as a hint: Enter, Esc, /, @."""
    return KeyCap(text, palette)


class ElidedLabel(QLabel):
    """One line that ends in an ellipsis instead of pushing its parent wider."""

    def __init__(self, text: str = "", parent: QWidget | None = None, mode: Any = Qt.TextElideMode.ElideRight):
        super().__init__(text, parent)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(1)
        self.setToolTip(text)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        shown = self.fontMetrics().elidedText(self.text(), self._mode, self.width())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), shown)
        painter.end()


def dot(colour: Any, size: int = 8) -> QLabel:
    label = QLabel()
    label.setFixedSize(QSize(size, size))
    label.setStyleSheet(f"QLabel {{ background: {style.css_color(colour)}; border-radius: {size // 2}px; }}")
    return label
