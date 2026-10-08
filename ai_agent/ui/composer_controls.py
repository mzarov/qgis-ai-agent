"""The composer's bottom row, after the design handoff: add context, the mode, the model, send.

"+" opens the add-to-context menu: a layer (opens the @ list), a file or table,
a picture, a skill (opens the / list). The mode button — shield, name, chevron —
opens the mode menu above the whole box. On the right sit the context ring, the
model's name in monospace and the round send button, a stop square while the
agent works. The name opens the connection settings; there is no model list,
since each endpoint is its own model (the user's call). Everything paints its
own hover.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase, QIcon, QPainter
from qgis.PyQt.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
from ai_agent.ui.choice_popup import ChoicePopup
from ai_agent.ui.chrome import IconButton
from ai_agent.ui.composer_parts import MODES
from ai_agent.ui.context_meter import ContextMeter

BUTTON_HEIGHT = 28
BUTTON_RADIUS = 6
PADDING = 6
LEAD = 14
LEAD_GAP = 5
CHEVRON = 12
CHEVRON_GAP = 4
MIN_TEXT = 24
# Text advances are fractional: a box exactly as wide as the rounded advance would elide its own text.
TEXT_SLACK = 2
SEND_SIZE = 28
SEND_ICON = 16
STOP_SIDE = 10
STOP_RADIUS = 2
DISABLED_OPACITY = 0.4
MODE_SCALE = 12.5 / 13
MODEL_SCALE = 12 / 13
ROW_MARGINS = (6, 4, 6, 6)
ADD_CONTEXT = tr("Add context")
ADD_CAPTION = tr("Add to context")
LAYER_ITEM = tr("Layer…")
FILE_ITEM = tr("File or table…")
PICTURE_ITEM = tr("Picture…")
SKILL_ITEM = tr("Skill…")
MODE_CAPTION = tr("Mode")
MODE_HINT = tr("How changes are applied. Shift+Tab switches.")
MODE_FOOTER = tr("Shift+Tab — next mode")
MODEL_HINT = tr("{0} — opens the connection settings")
NO_MODEL = tr("No model")
SEND = tr("Send")
STOP = tr("Stop")
SKILL_KEY = "/"


class MenuButton(QAbstractButton):
    """A flat button that opens a menu: an optional leading glyph, its text elided, a chevron after it."""

    def __init__(self, palette: Any, lead: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._lead = (icons.drawn(lead, style.muted(palette), LEAD), icons.drawn(lead, style.text(palette), LEAD))
        self._chevron = (
            icons.drawn("expanded", style.muted(palette), CHEVRON),
            icons.drawn("expanded", style.text(palette), CHEVRON),
        )
        self._has_lead = bool(lead) and self._lead[0] is not None
        self.setFixedHeight(BUTTON_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _frame_width(self) -> int:
        return 2 * PADDING + (LEAD + LEAD_GAP if self._has_lead else 0) + CHEVRON_GAP + CHEVRON

    def sizeHint(self) -> QSize:
        text = self.fontMetrics().horizontalAdvance(self.text()) + TEXT_SLACK
        return QSize(self._frame_width() + text, BUTTON_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._frame_width() + MIN_TEXT, BUTTON_HEIGHT)

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
            painter.drawRoundedRect(QRectF(self.rect()), BUTTON_RADIUS, BUTTON_RADIUS)
        state = 1 if hovered else 0
        x = PADDING
        lead = self._lead[state]
        if self._has_lead and lead is not None:
            painter.drawPixmap(x, (self.height() - LEAD) // 2, lead.pixmap(LEAD, LEAD))
            x += LEAD + LEAD_GAP
        room = max(0, self.width() - x - PADDING - CHEVRON_GAP - CHEVRON)
        shown = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, room)
        painter.setPen(style.text(self._palette) if hovered else style.muted(self._palette))
        painter.drawText(QRect(x, 0, room, self.height()), int(Qt.AlignmentFlag.AlignVCenter), shown)
        chevron = self._chevron[state]
        if chevron is not None:
            after = x + self.fontMetrics().horizontalAdvance(shown) + CHEVRON_GAP
            painter.drawPixmap(after, (self.height() - CHEVRON) // 2, chevron.pixmap(CHEVRON, CHEVRON))
        painter.end()


class SendButton(QAbstractButton):
    """The round send button: accent with an arrow, dimmed with nothing to send; a stop square while busy."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._arrow = icons.drawn("send", style.on_accent(palette), SEND_ICON)
        self.busy = False
        self.setFixedSize(SEND_SIZE, SEND_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_busy(False)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        name = STOP if busy else SEND
        self.setToolTip(name)
        self.setAccessibleName(name)
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
        circle = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        centre = self.width() / 2
        if self.busy:
            painter.setPen(style.border_strong(self._palette))
            painter.setBrush(style.card(self._palette))
            painter.drawEllipse(circle)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.text(self._palette))
            square = QRectF(centre - STOP_SIDE / 2, centre - STOP_SIDE / 2, STOP_SIDE, STOP_SIDE)
            painter.drawRoundedRect(square, STOP_RADIUS, STOP_RADIUS)
        else:
            hovered = self.isEnabled() and self.underMouse()
            if not self.isEnabled():
                painter.setOpacity(DISABLED_OPACITY)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.accent_hover(self._palette) if hovered else style.accent(self._palette))
            painter.drawEllipse(circle)
            if self._arrow is None:
                painter.setPen(style.on_accent(self._palette))
                painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "↑")
            else:
                corner = int(centre - SEND_ICON / 2)
                painter.drawPixmap(corner, corner, self._arrow.pixmap(SEND_ICON, SEND_ICON))
        painter.end()


class ComposerControls(QWidget):
    """The row at the bottom of the box: +, the mode, then the context ring, the model and send."""

    data_requested = pyqtSignal()
    picture_requested = pyqtSignal()
    layer_requested = pyqtSignal()
    skill_requested = pyqtSignal()
    mode_chosen = pyqtSignal(str)
    model_clicked = pyqtSignal()

    def __init__(self, palette: Any, count_layers: Callable[[], int] = lambda: 0, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._count_layers = count_layers
        self._anchor: QWidget = self
        row = QHBoxLayout(self)
        row.setContentsMargins(*ROW_MARGINS)
        row.setSpacing(2)
        self.attach = IconButton("new", "+", ADD_CONTEXT, palette, BUTTON_HEIGHT, 16)
        self.attach.clicked.connect(self._open_menu)
        row.addWidget(self.attach)
        self.menu = self._build_menu(palette)
        self.mode = MenuButton(palette, "mode")
        style.scale_font(self.mode, MODE_SCALE)
        self.mode.setToolTip(MODE_HINT)
        self.mode.setAccessibleName(MODE_HINT)
        self.modes = ChoicePopup(MODE_CAPTION, list(MODES), palette, MODE_FOOTER)
        self.modes.chosen.connect(self.mode_chosen.emit)
        self.mode.clicked.connect(self._open_modes)
        row.addWidget(self.mode)
        self._mode = MODES[0].key
        self.set_mode(self._mode)
        row.addStretch(1)
        self.meter = ContextMeter(palette)
        row.addWidget(self.meter, 0, Qt.AlignmentFlag.AlignVCenter)
        self.model = MenuButton(palette)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSizeF(max(1.0, self.font().pointSizeF() * MODEL_SCALE))
        self.model.setFont(mono)
        self.model.clicked.connect(self.model_clicked.emit)
        row.addWidget(self.model)
        self.send = SendButton(palette)
        row.addWidget(self.send)
        self.set_model("")

    def set_menu_anchor(self, anchor: QWidget) -> None:
        """The widget the mode menu spans and opens above: the whole box."""
        self._anchor = anchor

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.mode.setText(next((choice.title for choice in MODES if choice.key == mode), MODES[0].title))

    def set_model(self, name: str) -> None:
        shown = name.rsplit("/", 1)[-1] if name else NO_MODEL
        self.model.setText(shown)
        self.model.setToolTip(MODEL_HINT.format(name or NO_MODEL))

    def _build_menu(self, palette: Any) -> Any:
        menu = controls.menu(self.attach, palette)
        menu.addAction(controls.menu_caption(menu, ADD_CAPTION, palette))
        self._layer_action = menu.addAction(_glyph("layer", palette), LAYER_ITEM)
        self._layer_action.triggered.connect(self.layer_requested.emit)
        menu.addAction(_glyph("file", palette), FILE_ITEM).triggered.connect(self.data_requested.emit)
        menu.addAction(_glyph("image", palette), PICTURE_ITEM).triggered.connect(self.picture_requested.emit)
        menu.addSeparator()
        # After a tab, QMenu writes the text right-aligned in its shortcut column; no shortcut is bound.
        skill = menu.addAction(_glyph("knowledge", palette), f"{SKILL_ITEM}\t{SKILL_KEY}")
        skill.triggered.connect(self.skill_requested.emit)
        return menu

    def _open_menu(self) -> None:
        count = self._count_layers()
        self._layer_action.setText(f"{LAYER_ITEM}\t{count}" if count else LAYER_ITEM)
        # The composer sits at the bottom of the dock: the menu opens upwards, above the button.
        above = self.attach.mapToGlobal(QPoint(0, 0))
        self.menu.popup(QPoint(above.x(), above.y() - self.menu.sizeHint().height() - controls.MENU_GAP))

    def _open_modes(self) -> None:
        self.modes.open_above(self._anchor, self._mode, self._anchor.width())


def _glyph(role: str, palette: Any) -> QIcon:
    icon = icons.drawn(role, style.faint(palette), 16)
    return icon if icon is not None else QIcon()
