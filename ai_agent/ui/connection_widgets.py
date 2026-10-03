"""The Connection page's own widgets: provider tiles and the connection status card."""

from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.core.llm.providers import Preset
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, logos, style
from ai_agent.ui import settings_fields as fields

TILE_NAME = "providerTile"
STATUS_NAME = "connectionStatus"
MIN_TILE_WIDTH = 190
MIN_COLUMNS = 2
MAX_COLUMNS = 4
TILE_GAP = 8
TILE_HEIGHT = 58
MONOGRAM = 30
LOGO = 17
MONOGRAM_RADIUS = 7
MONOGRAM_SCALE = 0.8
SELECTED_EDGE = 2
LIGHT = 8
CONNECTION_TEST = tr("Connection test")
STATE_IDLE = "idle"
STATE_OK = "ok"
STATE_BAD = "bad"


def _logo(preset: Preset, palette: Any) -> Any:
    if preset.is_custom:
        icon = icons.drawn("connection", style.text(palette), LOGO)
        return None if icon is None else icon.pixmap(LOGO, LOGO)
    return logos.pixmap(preset.title, style.text(palette), LOGO)


def _initials(title: str) -> str:
    words = [word for word in title.replace("-", " ").split() if word[:1].isalnum()]
    return "".join(word[0] for word in words[:2]).upper() or "?"


class ProviderTile(controls.RoundedFrame):
    """A provider to pick; the chosen one gains a two-pixel accent edge, painted, not styled."""

    clicked = pyqtSignal(str)

    def __init__(self, preset: Preset, palette: Any):
        super().__init__(style.CARD_RADIUS)
        self.title = preset.title
        self.selected = False
        self._palette = palette
        self.setObjectName(TILE_NAME)
        self.setMinimumHeight(TILE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 9, 10, 9)
        line.setSpacing(8)
        monogram = QLabel()
        monogram.setFixedSize(MONOGRAM, MONOGRAM)
        monogram.setAlignment(Qt.AlignmentFlag.AlignCenter)
        monogram.setStyleSheet(
            f"QLabel {{ background: {style.css_color(style.card(palette))};"
            f"color: {style.css_color(style.text(palette))}; border-radius: {MONOGRAM_RADIUS}px; }}"
        )
        art = _logo(preset, palette)
        if art is not None:
            monogram.setPixmap(art)
        else:
            style.scale_font(monogram, MONOGRAM_SCALE, bold=True)
            monogram.setText(_initials(preset.title))
        line.addWidget(monogram)
        name = controls.ElidedLabel(preset.title)
        name.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(name, 1)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        border = style.accent(self._palette) if selected else style.hairline(self._palette)
        self.set_look(style.panel(self._palette).name(), border.name(), SELECTED_EDGE if selected else style.HAIRLINE)

    def mousePressEvent(self, _event: Any) -> None:
        self.clicked.emit(self.title)


class ProviderTiles(QWidget):
    """Every preset as a tile: local servers first, the custom address last."""

    chosen = pyqtSignal(str)

    def __init__(self, presets: list[Preset], palette: Any):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(TILE_GAP)
        ordered = [p for p in presets if not p.is_custom and not p.needs_key]
        ordered += [p for p in presets if not p.is_custom and p.needs_key]
        ordered += [p for p in presets if p.is_custom]
        self._tiles: list[ProviderTile] = []
        for preset in ordered:
            tile = ProviderTile(preset, palette)
            tile.clicked.connect(self.chosen.emit)
            self._tiles.append(tile)
        self._columns = 0
        self._arrange(MAX_COLUMNS - 1)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        # Columns follow the width: a larger system font or a narrow window gets fewer, wider tiles.
        fits = (self.width() + TILE_GAP) // (MIN_TILE_WIDTH + TILE_GAP)
        self._arrange(max(MIN_COLUMNS, min(MAX_COLUMNS, fits)))

    def _arrange(self, columns: int) -> None:
        if columns == self._columns:
            return
        for tile in self._tiles:
            self._grid.removeWidget(tile)
        for column in range(MAX_COLUMNS):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, index // columns, index % columns)
        self._columns = columns

    def select(self, title: str) -> None:
        for tile in self._tiles:
            tile.set_selected(tile.title == title)


class StatusCard(QFrame):
    """The connection test as one settings row: its name, a status line with a dot, the button."""

    def __init__(self, palette: Any, action: QWidget):
        super().__init__()
        self._palette = palette
        self.setObjectName(STATUS_NAME)
        line = QHBoxLayout(self)
        line.setContentsMargins(*fields.FLAT_ROW_PADDING)
        line.setSpacing(fields.ROW_GAP)
        text = QVBoxLayout()
        text.setSpacing(fields.FIELD_SPACING)
        name = QLabel(CONNECTION_TEST)
        name.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        text.addWidget(name)
        status = QHBoxLayout()
        status.setSpacing(7)
        self._light = controls.PaintedDot(LIGHT)
        status.addWidget(self._light, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = controls.small("", palette)
        self.title.setWordWrap(False)
        status.addWidget(self.title, 1)
        text.addLayout(status)
        self.detail = controls.small("", palette)
        text.addWidget(self.detail)
        line.addLayout(text, 1)
        line.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.state = STATE_IDLE
        self.show_state(STATE_IDLE, "", "")

    def show_state(self, state: str, title: str, detail: str) -> None:
        """One line of status; the detail shows only when something went wrong."""
        self.state = state
        colours = {STATE_OK: style.success(self._palette), STATE_BAD: style.danger(self._palette)}
        colour = colours.get(state, style.faint(self._palette))
        self._light.set_colour(colour.name())
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setStyleSheet(f"color: {style.css_color(style.danger(self._palette))};")
        self.detail.setVisible(state == STATE_BAD and bool(detail))
