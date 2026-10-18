"""Exclusive choices as tiles: providers on the Connection page, geocoders.

A tile is a rounded box on the surface: an optional logo, a name and a quiet
line under it, a radio at the right edge. The chosen one takes the accent edge
and the accent wash. Painted, not styled, so a click restyles nothing in its
own event. The grid gives each tile at least `min_width` and as many columns as
fit.
"""

from typing import Any

from qgis.PyQt.QtCore import QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPen
from qgis.PyQt.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.ui import controls, style

TILE_NAME = "choiceTile"
TILE_RADIUS = 8
TILE_MARGINS = (10, 10, 10, 10)
TILE_GAP = 8
RADIO = 14
RADIO_DOT = 6
NOTE_SCALE = 12 / 13


class Radio(QWidget):
    """A 14 px radio: a ring, the accent ring and dot when chosen."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.checked = False
        self.setFixedSize(RADIO, RADIO)

    def set_checked(self, checked: bool) -> None:
        if checked != self.checked:
            self.checked = checked
            self.update()

    def paintEvent(self, _event: Any) -> None:
        palette = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = style.accent(palette) if self.checked else style.border_strong(palette)
        painter.setPen(QPen(ring, style.HAIRLINE))
        painter.setBrush(style.surface(palette))
        painter.drawEllipse(QRectF(0.5, 0.5, RADIO - 1, RADIO - 1))
        if self.checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.accent(palette))
            inset = (RADIO - RADIO_DOT) / 2
            painter.drawEllipse(QRectF(inset, inset, RADIO_DOT, RADIO_DOT))
        painter.end()


class ChoiceTile(controls.RoundedFrame):
    """One choice: logo, name, a quiet line, the radio; a click picks it."""

    clicked = pyqtSignal(str)

    def __init__(self, key: str, title: str, note: str, palette: Any, logo: QWidget | None = None):
        super().__init__(TILE_RADIUS)
        self.key = key
        self.selected = False
        self._palette = palette
        self.setObjectName(TILE_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(*TILE_MARGINS)
        line.setSpacing(10)
        if logo is not None:
            line.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.name = controls.ElidedLabel(title)
        style.ink(self.name, style.text(palette))
        text.addWidget(self.name)
        self.note = QLabel(note)
        # Wrapping, never widening: a long note in Russian must not push the grid off the page.
        self.note.setWordWrap(True)
        style.scale_font(self.note, NOTE_SCALE)
        style.ink(self.note, style.faint(palette))
        text.addWidget(self.note)
        line.addLayout(text, 1)
        self.radio = Radio(palette)
        line.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignTop if not logo else Qt.AlignmentFlag.AlignVCenter)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        palette = self._palette
        fill = style.soft(palette, style.accent(palette)) if selected else style.surface(palette)
        border = style.accent(palette) if selected else style.hairline(palette)
        self.set_look(fill.name(), border.name())
        self.radio.set_checked(selected)

    def mousePressEvent(self, _event: Any) -> None:
        self.clicked.emit(self.key)


class TileGrid(QWidget):
    """Tiles in as many columns as fit at `min_width` each; a narrow window gets fewer, wider tiles."""

    chosen = pyqtSignal(str)

    def __init__(self, tiles: list[ChoiceTile], min_width: int, max_columns: int):
        super().__init__()
        self.tiles = tiles
        self._min_width = min_width
        self._max_columns = max_columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(TILE_GAP)
        for tile in tiles:
            tile.clicked.connect(self.chosen.emit)
        self._columns = 0
        self._arrange(max(1, max_columns - 1))

    def select(self, key: str) -> None:
        for tile in self.tiles:
            tile.set_selected(tile.key == key)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        fits = (self.width() + TILE_GAP) // (self._min_width + TILE_GAP)
        self._arrange(max(1, min(self._max_columns, fits)))

    def minimumSizeHint(self) -> QSize:
        return QSize(self._min_width, super().minimumSizeHint().height())

    def _arrange(self, columns: int) -> None:
        if columns == self._columns:
            return
        for tile in self.tiles:
            self._grid.removeWidget(tile)
        for column in range(self._max_columns):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, tile in enumerate(self.tiles):
            self._grid.addWidget(tile, index // columns, index % columns)
        self._columns = columns
