"""A drop-down that looks like the other settings fields and opens the panel's own menu.

A QComboBox draws as a bare text box once its arrow is styled away, and on
macOS its popup is the native one, deaf to the theme. This is a field with a
chevron that opens `controls.menu`: the current choice carries a check, the
others leave room for it. It keeps the slice of the QComboBox API the pages use.
Opening turns the chevron up and fades the menu in; closing turns it back.
"""

from typing import Any

from qgis.PyQt.QtCore import QEasingCurve, QPoint, QPointF, QSize, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ai_agent.ui import controls, icons, style

CHEVRON = 14
CHECK = 14
MENU_GAP = 4
RADIUS = 6
PADDING = (10, 6, 8, 6)
MIN_HEIGHT = 32
TURN_MS = 180
FADE_MS = 140
UP = 180.0


class Dropdown(QPushButton):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._items: list[tuple[str, Any]] = []
        self._current = -1
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(MIN_HEIGHT)
        border = style.css_color(style.border_strong(palette))
        self.setStyleSheet(
            f"QPushButton {{ background: {style.css_color(style.field(palette))};"
            f"border: {style.HAIRLINE}px solid {border}; border-radius: {RADIUS}px; text-align: left; }}"
            f"QPushButton:hover {{ border-color: {style.css_color(style.muted(palette))}; }}"
            f"QPushButton:focus {{ border-color: {style.css_color(style.accent(palette))}; }}"
        )
        line = QHBoxLayout(self)
        line.setContentsMargins(*PADDING)
        line.setSpacing(6)
        self._label = QLabel()
        style.ink(self._label, style.text(palette))
        line.addWidget(self._label, 1)
        self.chevron = Chevron(palette)
        line.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        self.clicked.connect(self._open)

    def addItem(self, text: str, data: Any = None) -> None:
        self._items.append((text, data))
        if self._current < 0:
            self.setCurrentIndex(0)

    def count(self) -> int:
        return len(self._items)

    def findData(self, data: Any) -> int:
        return next((index for index, (_text, value) in enumerate(self._items) if value == data), -1)

    def currentIndex(self) -> int:
        return self._current

    def currentData(self) -> Any:
        return self._items[self._current][1] if 0 <= self._current < len(self._items) else None

    def currentText(self) -> str:
        return self._items[self._current][0] if 0 <= self._current < len(self._items) else ""

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self._items) or index == self._current:
            return
        self._current = index
        self._label.setText(self._items[index][0])
        self.currentIndexChanged.emit(index)

    def _open(self) -> None:
        popup = controls.menu(self, self._palette)
        popup.setMinimumWidth(self.width())
        check = icons.drawn("check", style.accent(self._palette), CHECK)
        blank = _blank_icon()
        popup.setStyleSheet(popup.styleSheet() + f"QMenu {{ icon-size: {CHECK}px; }}")
        for index, (text, _data) in enumerate(self._items):
            action = popup.addAction(check if index == self._current and check is not None else blank, text)
            action.triggered.connect(lambda _checked=False, chosen=index: self.setCurrentIndex(chosen))
        fade = _animation(popup, FADE_MS, 0.0, 1.0, popup.setWindowOpacity)
        popup.setWindowOpacity(0.0)
        popup.aboutToShow.connect(fade.start)
        popup.aboutToHide.connect(lambda: self.chevron.turn(0.0))
        self.chevron.turn(UP)
        popup.exec(self.mapToGlobal(QPoint(0, self.height() + MENU_GAP)))

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), max(hint.height(), MIN_HEIGHT))


class Chevron(QWidget):
    """The field's arrow, painted at an angle so it can turn up and back smoothly."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(CHEVRON, CHEVRON)
        glyph = icons.drawn("expanded", style.muted(palette), CHEVRON)
        self._pixmap = glyph.pixmap(CHEVRON, CHEVRON) if glyph is not None else None
        self.angle = 0.0
        self._turning: Any = None

    def turn(self, angle: float) -> None:
        """Animate to `angle` degrees: 180 points up while the menu is open, 0 points down."""
        if self._turning is not None:
            self._turning.stop()
        self._turning = _animation(self, TURN_MS, self.angle, angle, self.set_angle)
        self._turning.start()

    def set_angle(self, angle: Any) -> None:
        self.angle = float(angle)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(QPointF(self.width() / 2, self.height() / 2))
        painter.rotate(self.angle)
        painter.drawPixmap(QPointF(-CHEVRON / 2, -CHEVRON / 2), self._pixmap)
        painter.end()


def _animation(owner: Any, duration: int, start: float, end: float, apply: Any) -> Any:
    """An eased value animation owned by `owner`, so Qt deletes it with the widget."""
    animation = QVariantAnimation(owner)
    animation.setDuration(duration)
    animation.setStartValue(float(start))
    animation.setEndValue(float(end))
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(apply)
    return animation


def _blank_icon() -> QIcon:
    """An empty icon the size of the check: unchecked rows stay aligned with the checked one."""
    pixmap = QPixmap(CHECK, CHECK)
    pixmap.fill(Qt.GlobalColor.transparent)
    return QIcon(pixmap)
