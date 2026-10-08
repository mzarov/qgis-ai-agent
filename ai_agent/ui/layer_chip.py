"""The active layer as a chip above the composer's text: the context the next request carries.

The orchestrator tells the dock which layer QGIS has active and what it holds
("Districts · 12 features"); the chip shows it with a × that drops it until the
active layer changes. A new request then names the layer with an @mention the
orchestrator appends, unless the request already names it — the model reads @name
as the exact name of a layer.
"""

from typing import Any

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style

CHIP_HEIGHT = 22
CHIP_RADIUS = 4
ICON = 12
TEXT_SCALE = 12 / 13
MAX_WIDTH = 280
SEPARATOR = " · "
DROP = tr("Leave this layer out of the request")


class LayerChip(controls.RoundedFrame):
    changed = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(CHIP_RADIUS, parent)
        self.name = ""
        self._dropped = ""
        self.set_look(style.card(palette).name(), style.hairline(palette).name())
        self.setFixedHeight(CHIP_HEIGHT)
        self.setMaximumWidth(MAX_WIDTH)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 2, 0)
        row.setSpacing(5)
        glyph = QLabel()
        glyph.setFixedSize(ICON, ICON)
        icon = icons.drawn("layer", style.muted(palette), ICON)
        if icon is not None:
            glyph.setPixmap(icon.pixmap(ICON, ICON))
        row.addWidget(glyph)
        self.label = controls.ElidedLabel()
        # As wide as its text while there is room; a long name elides instead of widening the box.
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        style.scale_font(self.label, TEXT_SCALE)
        style.ink(self.label, style.muted(palette))
        row.addWidget(self.label, 1)
        self.drop_button = QToolButton()
        self.drop_button.setFixedSize(CHIP_HEIGHT - 4, CHIP_HEIGHT - 4)
        self.drop_button.setAutoRaise(True)
        self.drop_button.setToolTip(DROP)
        self.drop_button.setAccessibleName(DROP)
        self.drop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drop_button.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 3px; }"
            f"QToolButton:hover {{ background: {style.css_color(style.sunken(palette))}; }}"
        )
        cross = icons.drawn("close", style.faint(palette), ICON)
        if cross is None:
            self.drop_button.setText("×")
        else:
            self.drop_button.setIcon(cross)
            self.drop_button.setIconSize(QSize(ICON, ICON))
        self.drop_button.clicked.connect(self.drop)
        row.addWidget(self.drop_button)
        self.setVisible(False)

    @property
    def active_name(self) -> str:
        """The layer the next request carries; empty when there is none or the user dropped it."""
        return self.name if self.name and self.name != self._dropped else ""

    def set_layer(self, name: str, detail: str = "") -> None:
        if name != self.name:
            # Another layer: a drop was about the previous one.
            self._dropped = ""
        self.name = name
        text = f"{name}{SEPARATOR}{detail}" if name and detail else name
        self.label.setText(text)
        self.label.setToolTip(text)
        self._show()

    def drop(self) -> None:
        self._dropped = self.name
        self._show()

    def _show(self) -> None:
        self.setVisible(bool(self.active_name))
        self.changed.emit()
