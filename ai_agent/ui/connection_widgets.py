"""The Connection page's own widgets: provider tiles and the connection test's line."""

from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.core.llm.providers import Preset
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, logos, style
from ai_agent.ui.choice_tiles import ChoiceTile, TileGrid

STATUS_NAME = "connectionStatus"
MIN_TILE_WIDTH = 180
MAX_COLUMNS = 3
MONOGRAM = 30
LOGO = 16
MONOGRAM_RADIUS = 6
MONOGRAM_SCALE = 0.8
LIGHT = 7
LOCAL = tr("Local")
CLOUD = tr("Cloud · key")
ANY_SERVER = tr("Any compatible server")
STATE_IDLE = "idle"
STATE_OK = "ok"
STATE_BAD = "bad"
OK_MARK = "✓"
BAD_MARK = "✕"


def _logo(preset: Preset, palette: Any) -> Any:
    if preset.is_custom:
        icon = icons.drawn("connection", style.text(palette), LOGO)
        return None if icon is None else icon.pixmap(LOGO, LOGO)
    return logos.pixmap(preset.title, style.text(palette), LOGO)


def _initials(title: str) -> str:
    words = [word for word in title.replace("-", " ").split() if word[:1].isalnum()]
    return "".join(word[0] for word in words[:2]).upper() or "?"


def _monogram(preset: Preset, palette: Any) -> QLabel:
    tile = QLabel()
    tile.setFixedSize(MONOGRAM, MONOGRAM)
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tile.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.sunken(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"color: {style.css_color(style.muted(palette))}; border-radius: {MONOGRAM_RADIUS}px; }}"
    )
    art = _logo(preset, palette)
    if art is not None:
        tile.setPixmap(art)
    else:
        style.scale_font(tile, MONOGRAM_SCALE, bold=True)
        tile.setText(_initials(preset.title))
    return tile


def _note(preset: Preset) -> str:
    if preset.is_custom:
        return ANY_SERVER
    return CLOUD if preset.needs_key else LOCAL


class ProviderTiles(TileGrid):
    """Every preset as a tile, local servers first and the custom address last; keyed by the preset's title."""

    def __init__(self, presets: list[Preset], palette: Any):
        ordered = [p for p in presets if not p.is_custom and not p.needs_key]
        ordered += [p for p in presets if not p.is_custom and p.needs_key]
        ordered += [p for p in presets if p.is_custom]
        tiles = [ChoiceTile(p.title, p.title, _note(p), palette, _monogram(p, palette)) for p in ordered]
        super().__init__(tiles, MIN_TILE_WIDTH, MAX_COLUMNS)


class StatusCard(QWidget):
    """The connection test as one line under the fields: the button, then what it found."""

    def __init__(self, palette: Any, action: QWidget):
        super().__init__()
        self._palette = palette
        self.setObjectName(STATUS_NAME)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        line = QHBoxLayout()
        line.setSpacing(10)
        line.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self._light = controls.PaintedDot(LIGHT)
        line.addWidget(self._light, 0, Qt.AlignmentFlag.AlignVCenter)
        self._mark = QLabel()
        line.addWidget(self._mark, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = controls.small("", palette)
        self.title.setWordWrap(False)
        line.addWidget(self.title, 1, Qt.AlignmentFlag.AlignVCenter)
        column.addLayout(line)
        self.detail = controls.small("", palette)
        column.addWidget(self.detail)
        self.state = STATE_IDLE
        self.show_state(STATE_IDLE, "", "")

    def show_state(self, state: str, title: str, detail: str) -> None:
        """One line of status; the detail shows only when something went wrong."""
        self.state = state
        palette = self._palette
        colours = {STATE_OK: style.success(palette), STATE_BAD: style.danger(palette)}
        colour = colours.get(state, style.faint(palette))
        # A check or a cross says it in so many words; the dot is for not tested and testing.
        self._light.set_colour(colour.name())
        self._light.setVisible(state == STATE_IDLE)
        self._mark.setText(OK_MARK if state == STATE_OK else BAD_MARK if state == STATE_BAD else "")
        self._mark.setVisible(state != STATE_IDLE)
        style.ink(self._mark, colour)
        self.title.setText(title)
        style.ink(self.title, colour if state != STATE_IDLE else style.muted(palette))
        self.detail.setText(detail)
        style.ink(self.detail, style.danger(palette))
        self.detail.setVisible(state == STATE_BAD and bool(detail))
