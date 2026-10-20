from collections.abc import Callable
from html import escape
from typing import Any

from qgis.PyQt.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ai_agent.ui import icons, style, transitions

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
MENU_RADIUS = 8
MENU_ITEM_RADIUS = 5
MENU_GAP = 4
CAPTION_SCALE = 11 / 13
KEY_SCALE = 0.8
KEY_PADDING = 5
KEY_MIN_WIDTH = 18
KEY_EXTRA_HEIGHT = 4
KEY_EDGE_TINT = 0.35
SMALL_SCALE = 0.85
BAR_HEIGHT = 2
SWEEP_MS = 1200
SWEEP_SHARE = 0.3
REST_PHASE = 0.5
SWATCH_RADIUS = 2
NEWLINE = "\n"
LINE_BREAK = "<br>"


class Segmented(QFrame):
    currentIndexChanged = pyqtSignal(int)
    currentTextChanged = pyqtSignal(str)

    def __init__(self, palette: Any):
        super().__init__()
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

    def _clicked(self, index: int) -> None:
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
    def __init__(
        self,
        palette: Any,
        edit: QLineEdit,
        presets: list[tuple[str, str]],
        parse: Callable[[str], int | None],
    ):
        super().__init__()
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
            chip.setStyleSheet(chip_style(palette))
            chip.clicked.connect(lambda _checked=False, text=value: self._edit.setText(text))
            line.addWidget(chip)
            self._chips.append((chip, parse(value)))
        edit.textChanged.connect(self._sync)
        self._sync(edit.text())

    def _sync(self, text: str) -> None:
        value = self._parse(text)
        for chip, preset in self._chips:
            chip.setChecked(value is not None and value == preset)


def chip_style(palette: Any) -> str:
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


# Painted, not styled: a style sheet swapped while a child is in its event handler crashes QGIS.
class RoundedFrame(QFrame):
    def __init__(self, radius: float, parent: QWidget | None = None):
        super().__init__(parent)
        self._radius = radius
        self._look: tuple[Any, Any] | None = None

    def set_look(self, fill: Any, border: Any) -> None:
        look = (fill, border)
        if look != self._look:
            self._look = look
            self.update()

    def paintEvent(self, _event: Any) -> None:
        if self._look is None or self._look == (None, None):
            return
        fill, border = self._look
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if border is None:
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            pen = QPen(QColor(border))
            pen.setWidthF(style.HAIRLINE)
            painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush if fill is None else QColor(fill))
        inset = style.HAIRLINE / 2
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), self._radius, self._radius)
        painter.end()


class HoverFrame(RoundedFrame):
    clicked = pyqtSignal()

    def __init__(self, radius: float, palette: Any):
        super().__init__(radius)
        self._fill = style.card(palette).name()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event: Any) -> None:
        self.set_look(self._fill, None)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.set_look(None, None)
        super().leaveEvent(event)


class PaintedDot(QWidget):
    def __init__(self, size: int):
        super().__init__()
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


class PaintedSwatch(QWidget):
    def __init__(self, size: int, colour: str, edge: Any):
        super().__init__()
        self.colour = colour
        self._edge = edge
        self.setFixedSize(size, size)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._edge, style.HAIRLINE))
        painter.setBrush(QColor(self.colour))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), SWATCH_RADIUS, SWATCH_RADIUS)
        painter.end()


class ThinBar(QWidget):
    def __init__(self, palette: Any):
        super().__init__()
        self._track = style.hairline(palette)
        self._fill = style.accent(palette)
        self.fraction = 0.0
        self.running = False
        self._phase = 0.0
        self._sweep: QVariantAnimation | None = None
        self.setFixedHeight(BAR_HEIGHT)

    def set_fraction(self, value: float) -> None:
        self._stop_sweep()
        value = min(max(float(value), 0.0), 1.0)
        if value != self.fraction:
            self.fraction = value
            self.update()

    def set_running(self) -> None:
        if self._sweep is None:
            self._sweep = QVariantAnimation(self)
            self._sweep.setStartValue(0.0)
            self._sweep.setEndValue(1.0)
            self._sweep.setDuration(SWEEP_MS)
            self._sweep.setLoopCount(-1)
            self._sweep.valueChanged.connect(self._swept)
        self.running = True
        if self._sweep.state() != QVariantAnimation.State.Running:
            self._sweep.start()

    def rest(self) -> None:
        if self._sweep is not None:
            self._sweep.stop()
        self._swept(REST_PHASE)

    def hideEvent(self, event: Any) -> None:
        self._stop_sweep()
        super().hideEvent(event)

    def _stop_sweep(self) -> None:
        self.running = False
        if self._sweep is not None:
            self._sweep.stop()

    def _swept(self, value: Any) -> None:
        self._phase = float(value)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2
        painter.setBrush(self._track)
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
        painter.setBrush(self._fill)
        if self.running:
            segment = self.width() * SWEEP_SHARE
            left = self._phase * (self.width() + segment) - segment
            painter.drawRoundedRect(QRectF(left, 0, segment, self.height()), radius, radius)
        elif self.fraction > 0:
            painter.drawRoundedRect(QRectF(0, 0, self.width() * self.fraction, self.height()), radius, radius)
        painter.end()


def menu(parent: QWidget, palette: Any) -> QMenu:
    popup = QMenu(parent)
    try:
        flags = popup.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
    except TypeError:
        flags = None
    if flags is not None:
        popup.setWindowFlags(flags)
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    transitions.DropIn(popup)
    popup.setStyleSheet(
        f"QMenu {{ background: {style.css_color(style.surface(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.border_strong(palette))};"
        f"border-radius: {MENU_RADIUS}px; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 12px 6px 10px; border-radius: {MENU_ITEM_RADIUS}px;"
        f"color: {style.css_color(style.text(palette))}; background: transparent; }}"
        f"QMenu::item:selected {{ background: {style.css_color(style.card(palette))}; }}"
        f"QMenu::item:disabled {{ color: {style.css_color(style.faint(palette))}; }}"
        f"QMenu::separator {{ height: {style.HAIRLINE}px; margin: 4px 6px;"
        f"background: {style.css_color(style.hairline(palette))}; }}"
    )
    return popup


def as_popup(window: QWidget) -> None:
    try:
        flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
    except TypeError:
        flags = None
    if flags is not None:
        window.setWindowFlags(flags)
    # A popup is a window of its own: it does not inherit the panel's palette.
    style.apply_palette(window)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    transitions.DropIn(window)


def caption(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    style.scale_font(label, CAPTION_SCALE, bold=True)
    font = label.font()
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    label.setFont(font)
    style.ink(label, style.faint(palette))
    label.setContentsMargins(10, 6, 10, 4)
    return label


def menu_rule(palette: Any) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(6, 4, 6, 4)
    rule = QWidget()
    rule.setFixedHeight(style.HAIRLINE)
    style.fill(rule, style.hairline(palette))
    line.addWidget(rule)
    return holder


def menu_caption(popup: QMenu, text: str, palette: Any) -> QWidgetAction:
    action = QWidgetAction(popup)
    action.setDefaultWidget(caption(text, palette))
    return action


def icon_tile(role: str, palette: Any, tile: int, size: int, radius: int, fallback: str) -> QLabel:
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


def glyph(role: str, colour: Any, size: int) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    icon = icons.drawn(role, colour, size)
    if icon is not None:
        label.setPixmap(icon.pixmap(size, size))
    return label


def icon_button(
    role: str, fallback: str, tooltip: str, colour: Any, palette: Any, side: int, icon: int, radius: int
) -> QToolButton:
    button = QToolButton()
    button.setFixedSize(side, side)
    button.setAutoRaise(True)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        f"QToolButton {{ border: none; background: transparent; border-radius: {radius}px; }}"
        f"QToolButton:hover {{ background: {style.css_color(style.sunken(palette))}; }}"
    )
    drawn = icons.drawn(role, colour, icon)
    if drawn is None:
        button.setText(fallback)
    else:
        button.setIcon(drawn)
        button.setIconSize(QSize(icon, icon))
    return button


def is_new_shortcut(event: Any) -> bool:
    matches = getattr(event, "matches", None)
    return bool(matches is not None and matches(QKeySequence.StandardKey.New) is True)


def small(text: str, palette: Any, scale: float = SMALL_SCALE) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    style.scale_font(label, scale)
    style.ink(label, style.muted(palette))
    return label


def badge(text: str, kind: str, palette: Any) -> QLabel:
    label = QLabel(text)
    style.scale_font(label, SMALL_SCALE, bold=True)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    colour = style.warning(palette) if kind == "warn" else style.accent(palette)
    fill = style.soft(palette, colour)
    ink = style.accent_ink(palette) if kind == "accent" else colour
    label.setStyleSheet(
        f"QLabel {{ background: {style.css_color(fill)}; color: {style.css_color(ink)};"
        f"border-radius: {BADGE_RADIUS}px; padding: 1px 7px; }}"
    )
    return label


class KeyCap(QLabel):
    def __init__(self, text: str, palette: Any):
        super().__init__(text)
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


def plain_tip(text: str) -> str:
    # Rich, so a long tip wraps; escaped, so a tag in it is shown, never followed.
    return f"<qt>{escape(text, quote=False).replace(NEWLINE, LINE_BREAK)}</qt>" if text else ""


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", mode: Any = Qt.TextElideMode.ElideRight):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setText(text)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(1)
        self.setToolTip(text)

    def setToolTip(self, text: str) -> None:
        super().setToolTip(plain_tip(text))

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        shown = self.fontMetrics().elidedText(self.text(), self._mode, self.width())
        across = self.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
        painter.drawText(self.rect(), int(across | Qt.AlignmentFlag.AlignVCenter), shown)
        painter.end()
