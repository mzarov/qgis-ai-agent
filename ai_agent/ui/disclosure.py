"""A fold line in Claude Code's manner: a title, an optional detail, then a chevron.

The whole line is the click target, not only the chevron, and the title brightens
on hover. Colours go through the label palettes: a style sheet changed from a
hover event would restyle the subtree in the middle of event processing.
"""

from typing import Any

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from ai_agent.ui import controls, icons, style

CHEVRON = 14
COLLAPSED = "›"
EXPANDED = "⌄"
DETAIL_SCALE = 0.9


class Disclosure(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._rest = style.muted(palette)
        self._hover = style.text(palette)
        self._chevron_colour = style.muted(palette)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)

        # Full width while there is room, an ellipsis when the dock is narrow: a long title must not widen it.
        self.title = controls.ElidedLabel()
        self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        style.ink(self.title, self._rest)
        self._row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)

        self.detail = QLabel()
        style.ink(self.detail, style.muted(palette))
        style.scale_font(self.detail, DETAIL_SCALE)
        self.detail.setVisible(False)
        self._row.addWidget(self.detail, 0, Qt.AlignmentFlag.AlignVCenter)

        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle.setIconSize(QSize(CHEVRON, CHEVRON))
        self.toggle.setFixedSize(CHEVRON + 2, CHEVRON + 2)
        self.toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0;"
            f"color: {style.css_color(self._chevron_colour)}; }}"
        )
        self.toggle.toggled.connect(self._on_toggled)
        self._row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        self._row.addStretch(1)
        self._show_chevron(False)

    def set_detail(self, text: str) -> None:
        # An empty label still costs two spacings: the chevron would drift off the title.
        self.detail.setText(text)
        self.detail.setVisible(bool(text))

    def add_note(self, widget: QWidget) -> None:
        """Put a widget after the title and detail, before the chevron."""
        self._row.insertWidget(self._row.indexOf(self.toggle), widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle.setChecked(not self.toggle.isChecked())

    def enterEvent(self, event: Any) -> None:
        style.ink(self.title, self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        style.ink(self.title, self._rest)
        super().leaveEvent(event)

    def _on_toggled(self, expanded: bool) -> None:
        self._show_chevron(expanded)
        self.toggled.emit(expanded)

    def _show_chevron(self, expanded: bool) -> None:
        icon = icons.chevron(expanded, self._chevron_colour, CHEVRON)
        if icon.isNull():
            self.toggle.setText(EXPANDED if expanded else COLLAPSED)
        else:
            self.toggle.setIcon(icon)
