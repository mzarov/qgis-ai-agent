"""The active layer as a chip above the composer's text: the context the next request carries.

The orchestrator tells the dock which layer QGIS has active and what it holds
("Districts · 12 features"); the chip shows it with a × that drops it until the
active layer changes. A new request then names the layer with an @mention the
orchestrator appends, unless the request already names it — the model reads @name
as the exact name of a layer.
"""

from typing import Any

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui.attachments import CHIP_HEIGHT, CHIP_RADIUS, ICON, TEXT_SCALE, chip_close

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
        row.addWidget(controls.glyph("layer", style.muted(palette), ICON))
        self.label = controls.ElidedLabel()
        # As wide as its text while there is room; a long name elides instead of widening the box.
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        style.scale_font(self.label, TEXT_SCALE)
        style.ink(self.label, style.muted(palette))
        row.addWidget(self.label, 1)
        self.drop_button = chip_close(DROP, palette)
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
