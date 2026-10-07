"""Small custom controls for the settings window and the composer.

`Segmented` keeps the slice of the `QComboBox` API the dialog already relies
on (`currentText`, `findText`, `setCurrentIndex`, item data, the change
signals), so saving and loading code reads it exactly like the combo box it
replaces. Everything is drawn from the palette through `style`.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ai_agent.ui import icons, style

SEGMENT_NAME = "segmented"
SEGMENT_RADIUS = 8
SEGMENT_INNER_RADIUS = 6
SEGMENT_PADDING = 12
SEGMENT_SLACK = 4
SLIDE_MS = 200
CHIP_HEIGHT = 26
CHIP_RADIUS = CHIP_HEIGHT // 2
BADGE_RADIUS = 8
KEY_RADIUS = 4
MENU_RADIUS = 10
MENU_ITEM_RADIUS = 6
MENU_GAP = 4
KEY_SCALE = 0.8
KEY_PADDING = 5
KEY_MIN_WIDTH = 18
KEY_EXTRA_HEIGHT = 4
KEY_EDGE_TINT = 0.35
SMALL_SCALE = 0.85


class Segmented(QFrame):
    """Mutually exclusive choices in one pill; reads like a combo box.

    The highlight under the chosen label is painted by the frame, not by the
    button, so a click slides it from the old choice to the new one.
    """

    currentIndexChanged = pyqtSignal(int)
    currentTextChanged = pyqtSignal(str)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._items: list[str] = []
        self._data: dict[int, Any] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._clicked)
        self._last = 0
        self._pill: QRectF | None = None
        self._slide: Any = None
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
            # Room for the bold checked label: sized for the regular weight, "Balanced" lost its last letter.
            bold = button.font()
            bold.setWeight(QFont.Weight.DemiBold)
            button.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(item) + 2 * SEGMENT_PADDING + SEGMENT_SLACK)
            self._group.addButton(button, len(self._items))
            self._line.addWidget(button)
            self._items.append(item)
        if self._group.checkedId() < 0 and self._items:
            self._group.button(0).setChecked(True)

    def addItem(self, text: str, data: Any = None) -> None:
        self.addItems([text])
        self._data[len(self._items) - 1] = data

    def findData(self, data: Any) -> int:
        return next((index for index, value in self._data.items() if value == data), -1)

    def currentData(self) -> Any:
        return self._data.get(self.currentIndex())

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

    def _clicked(self, index: int) -> None:
        """Slide the highlight from where it is now to the chosen label, then report the choice."""
        previous = self._group.button(self._last)
        start = self._pill or (QRectF(previous.geometry()) if previous is not None else None)
        target = self._group.button(index)
        if start is not None and target is not None and index != self._last:
            if self._slide is not None:
                self._slide.stop()
            self._slide = QVariantAnimation(self)
            self._slide.setDuration(SLIDE_MS)
            self._slide.setStartValue(start)
            self._slide.setEndValue(QRectF(target.geometry()))
            self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._slide.valueChanged.connect(self._move_pill)
            self._slide.finished.connect(self._slide_done)
            self._slide.start()
        self._chosen(index)

    def _slide_done(self) -> None:
        self._move_pill(None)

    def _move_pill(self, rect: Any) -> None:
        self._pill = QRectF(rect) if rect is not None else None
        self.update()

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        checked = self._group.button(self.currentIndex())
        rect = self._pill or (QRectF(checked.geometry()) if checked is not None else None)
        if rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(style.panel(self._palette))
        painter.drawRoundedRect(rect, SEGMENT_INNER_RADIUS, SEGMENT_INNER_RADIUS)
        painter.end()

    def _chosen(self, index: int) -> None:
        self._last = index
        self.currentIndexChanged.emit(index)
        self.currentTextChanged.emit(self.itemText(index))

    def _segment_style(self) -> str:
        return (
            f"QPushButton {{ background: transparent; border: none; border-radius: {SEGMENT_INNER_RADIUS}px;"
            f"padding: 4px {SEGMENT_PADDING}px; color: {style.css_color(style.muted(self._palette))}; }}"
            f"QPushButton:hover {{ color: {style.css_color(style.text(self._palette))}; }}"
            f"QPushButton:checked {{ background: transparent;"
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
        return chip_style(self._palette)


def chip_style(palette: Any) -> str:
    """A pill button: hairline at rest, an accent wash when checked."""
    accent = style.accent(palette)
    return (
        f"QPushButton {{ background: {style.css_color(style.panel(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.border_strong(palette))};"
        f"border-radius: {CHIP_RADIUS}px; padding: 0px 11px; }}"
        f"QPushButton:checked {{ background: {style.css_color(style.soft(palette, accent))};"
        f"border-color: {style.css_color(accent)}; color: {style.css_color(style.accent_ink(palette))};"
        "font-weight: 600; }"
    )


class RoundedFrame(QFrame):
    """A rounded box painted by hand; its look changes with `update()` and nothing else.

    A style sheet on a frame cascades to every child. Swapping it while a child
    was inside its own event handler (the composer editor's focusOut) crashed QGIS
    in event processing, so frames whose look follows state are painted.
    """

    def __init__(self, radius: float, parent: QWidget | None = None):
        super().__init__(parent)
        self._radius = radius
        self._look: tuple[Any, Any, float] | None = None

    def set_look(self, fill: Any, border: Any, width: float = style.HAIRLINE) -> None:
        """Fill and border colours, either None for none, and the border width."""
        look = (fill, border, width)
        if look != self._look:
            self._look = look
            self.update()

    def paintEvent(self, _event: Any) -> None:
        if self._look is None or self._look[:2] == (None, None):
            return
        fill, border, width = self._look
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if border is None:
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            pen = QPen(QColor(border))
            pen.setWidthF(width)
            painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush if fill is None else QColor(fill))
        inset = width / 2
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), self._radius, self._radius)
        painter.end()


class PaintedDot(QWidget):
    """A round status dot drawn by hand, recoloured with `set_colour` and no style sheet."""

    def __init__(self, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self.colour = ""
        self.setFixedSize(size, size)

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
        painter.drawEllipse(QRectF(0, 0, self._size, self._size))
        painter.end()


def menu(parent: QWidget, palette: Any) -> QMenu:
    """A popup menu in the panel's own look: rounded, soft edge, roomy rows, quiet highlight.

    Frameless and translucent so the rounded corners are not drawn over a square system frame.
    """
    popup = QMenu(parent)
    try:
        flags = popup.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
    except TypeError:
        flags = None
    if flags is not None:
        popup.setWindowFlags(flags)
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    popup.setStyleSheet(
        f"QMenu {{ background: {style.css_color(style.surface(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"border-radius: {MENU_RADIUS}px; padding: 5px; }}"
        f"QMenu::item {{ padding: 7px 16px 7px 12px; border-radius: {MENU_ITEM_RADIUS}px;"
        f"color: {style.css_color(style.text(palette))}; background: transparent; }}"
        f"QMenu::item:selected {{ background: {style.css_color(style.card(palette))}; }}"
        f"QMenu::item:disabled {{ color: {style.css_color(style.faint(palette))}; }}"
        f"QMenu::separator {{ height: {style.HAIRLINE}px; margin: 5px 8px;"
        f"background: {style.css_color(style.hairline(palette))}; }}"
    )
    return popup


def icon_tile(role: str, palette: Any, tile: int, size: int, radius: int, fallback: str) -> QLabel:
    """A glyph centred on a rounded card-coloured square; the fallback text when it cannot be drawn."""
    label = QLabel()
    label.setFixedSize(tile, tile)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.text(palette))}; border-radius: {radius}px; }}"
    )
    icon = icons.drawn(role, style.muted(palette), size)
    if icon is None:
        label.setText(fallback)
    else:
        label.setPixmap(icon.pixmap(size, size))
    return label


def small(text: str, palette: Any, scale: float = SMALL_SCALE) -> QLabel:
    """A muted, wrapping caption a step below the body text."""
    label = QLabel(text)
    label.setWordWrap(True)
    style.scale_font(label, scale)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label


def badge(text: str, kind: str, palette: Any) -> QLabel:
    """A small pill: neutral, ok, warn, accent or bad."""
    label = QLabel(text)
    style.scale_font(label, SMALL_SCALE, bold=True)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
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
    return label


class KeyCap(QLabel):
    """A keyboard key drawn by hand: a rounded outline, a slightly heavier bottom edge, the glyph centred.

    Style sheets cannot do this reliably: a thicker bottom border shifts the text off centre, and a
    hairline border all but disappears on a dark palette.
    """

    def __init__(self, text: str, palette: Any, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._palette = palette
        style.scale_font(self, KEY_SCALE)
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
