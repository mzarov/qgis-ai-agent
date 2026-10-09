"""The panel's chrome after the design handoff: the dock's own title bar and the toolbar under it.

The title bar replaces the native one: the still compass, "AI Agent", and float
and close buttons. A press anywhere else on it is left to the dock, so the panel
drags, docks and floats on a double click as before. The toolbar names the open
conversation — a button that opens the history — and holds two icon buttons:
a new conversation (disabled while the conversation is empty; its plus turns
when pressed) and the settings. Buttons paint their hover; nothing restyles in
an event.
"""

from typing import Any

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QAbstractButton, QDockWidget, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import compass, controls, icons, style

TITLE = "AI Agent"
TITLE_BAR_HEIGHT = 26
TITLE_BAR_MARGINS = (10, 0, 6, 0)
TITLE_MARK = 14
TITLE_SCALE = 12 / 13
TITLE_BUTTON = 20
TITLE_ICON = 14
TOOLBAR_HEIGHT = 40
TOOLBAR_MARGINS = (8, 0, 6, 0)
TOOL_BUTTON = 28
TOOL_ICON = 16
TOOL_RADIUS = 6
CHEVRON = 14
SPIN_DEGREES = 180.0
SPIN_MS = 400
# The handoff's transition for the plus: cubic-bezier(.3,.7,.3,1).
SPIN_EASING = (0.3, 0.7, 0.3, 1.0)
DISABLED_OPACITY = 0.55
FLOAT = tr("Float")
CLOSE = tr("Close")
NEW_CONVERSATION = tr("New conversation")
SETTINGS = tr("Settings")
HISTORY = tr("Conversation history")


class IconButton(QAbstractButton):
    """A square icon button: a rounded plate under the pointer, the glyph turned by `angle` degrees.

    Painted rather than styled, so hover and the turn are repaints. A glyph that cannot be drawn
    falls back to its text.
    """

    def __init__(self, role: str, fallback: str, tooltip: str, palette: Any, size: int, icon: int, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._icon_size = icon
        self._fallback = fallback
        self._rest = icons.drawn(role, style.muted(palette), icon)
        self._hover = icons.drawn(role, style.text(palette), icon)
        self.angle = 0.0
        self._spin: Any = None
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def spin(self) -> None:
        """Turn the glyph half a circle, once."""
        if self._spin is not None:
            self._spin.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(SPIN_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        # A bound method: Qt drops the connection with the button, a lambda would outlive it.
        animation.valueChanged.connect(self._turn)
        self._spin = animation
        animation.start()

    def _turn(self, progress: Any) -> None:
        self.angle = SPIN_DEGREES * compass.cubic_bezier(SPIN_EASING, float(progress))
        self.update()

    def enterEvent(self, event: Any) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.isEnabled() and self.underMouse()
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.card(self._palette))
            painter.drawRoundedRect(QRectF(self.rect()), TOOL_RADIUS, TOOL_RADIUS)
        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)
        icon = self._hover if hovered else self._rest
        if icon is None:
            painter.setPen(style.muted(self._palette))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._fallback)
        else:
            centre = QPointF(self.width() / 2, self.height() / 2)
            painter.translate(centre)
            painter.rotate(self.angle)
            half = self._icon_size // 2
            painter.drawPixmap(-half, -half, icon.pixmap(self._icon_size, self._icon_size))
        painter.end()


class DockTitleBar(QWidget):
    """The dock's title bar: the still mark, the name, float and close."""

    def __init__(self, dock: QDockWidget, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._dock = dock
        self._palette = palette
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        style.fill(self, style.card(palette))
        row = QHBoxLayout(self)
        row.setContentsMargins(*TITLE_BAR_MARGINS)
        row.setSpacing(6)
        # Still: the panel's one live compass is the status line's.
        self.mark = compass.Compass(TITLE_MARK, palette, halo=style.card(palette))
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        title = QLabel(TITLE)
        style.scale_font(title, TITLE_SCALE, bold=True)
        style.ink(title, style.text(palette))
        row.addWidget(title, 1)
        self.float_button = IconButton("float", "⧉", FLOAT, palette, TITLE_BUTTON, TITLE_ICON)
        self.float_button.clicked.connect(self._toggle_floating)
        row.addWidget(self.float_button)
        self.close_button = IconButton("close", "×", CLOSE, palette, TITLE_BUTTON, TITLE_ICON)
        self.close_button.clicked.connect(dock.close)
        row.addWidget(self.close_button)

    def _toggle_floating(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        _bottom_hairline(self, self._palette)


class TitleButton(controls.RoundedFrame):
    """The open conversation's title, bold and elided, with a chevron; a click opens the history."""

    clicked = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(TOOL_RADIUS, parent)
        self._palette = palette
        self.setFixedHeight(TOOL_BUTTON)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(HISTORY)
        self.setAccessibleName(HISTORY)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(4)
        self.label = controls.ElidedLabel()
        # As wide as its text while there is room, so the chevron follows the title; elided below that.
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        font = self.label.font()
        font.setBold(True)
        self.label.setFont(font)
        style.ink(self.label, style.text(palette))
        row.addWidget(self.label)
        chevron = QLabel()
        chevron.setFixedSize(CHEVRON, CHEVRON)
        icon = icons.drawn("expanded", style.faint(palette), CHEVRON)
        if icon is not None:
            chevron.setPixmap(icon.pixmap(CHEVRON, CHEVRON))
        row.addWidget(chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

    def set_title(self, title: str) -> None:
        self.label.setText(title)
        self.label.setToolTip(title)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event: Any) -> None:
        self.set_look(style.card(self._palette).name(), None)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.set_look(None, None)
        super().leaveEvent(event)


class Toolbar(QWidget):
    """The row under the title bar: the conversation's title, a new conversation, the settings."""

    history_requested = pyqtSignal()
    new_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.setFixedHeight(TOOLBAR_HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(*TOOLBAR_MARGINS)
        row.setSpacing(4)
        self.title = TitleButton(palette)
        self.title.clicked.connect(self.history_requested.emit)
        row.addWidget(self.title, 1)
        self.new_button = IconButton("new", "+", NEW_CONVERSATION, palette, TOOL_BUTTON, TOOL_ICON)
        self.new_button.clicked.connect(self._new)
        row.addWidget(self.new_button)
        self.settings_button = IconButton("settings", "⚙", SETTINGS, palette, TOOL_BUTTON, TOOL_ICON)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        row.addWidget(self.settings_button)

    def _new(self) -> None:
        self.new_button.spin()
        self.new_requested.emit()

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        _bottom_hairline(self, self._palette)


def _bottom_hairline(widget: QWidget, palette: Any) -> None:
    painter = QPainter(widget)
    painter.fillRect(0, widget.height() - style.HAIRLINE, widget.width(), style.HAIRLINE, style.hairline(palette))
    painter.end()
