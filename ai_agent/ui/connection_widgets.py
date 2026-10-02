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
LIGHT = 10
LOCAL_BADGE = tr("local · no key")
CLOUD = tr("cloud")
ANY_SERVER = tr("any OpenAI-compatible")
STATE_IDLE = "idle"
STATE_OK = "ok"
STATE_BAD = "bad"


def _logo(preset: Preset, palette: Any) -> Any:
    if preset.is_custom:
        try:
            return icons.connection(style.text(palette), LOGO).pixmap(LOGO, LOGO)
        except Exception:
            return None
    return logos.pixmap(preset.title, style.text(palette), LOGO)


def _initials(title: str) -> str:
    words = [word for word in title.replace("-", " ").split() if word[:1].isalnum()]
    return "".join(word[0] for word in words[:2]).upper() or "?"


class ProviderTile(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, preset: Preset, palette: Any):
        super().__init__()
        self.title = preset.title
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
            font = monogram.font()
            font.setBold(True)
            font.setPointSizeF(max(1.0, font.pointSizeF() * 0.8))
            monogram.setFont(font)
            monogram.setText(_initials(preset.title))
        line.addWidget(monogram)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addStretch(1)
        name = controls.ElidedLabel(preset.title)
        name.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        text.addWidget(name)
        if preset.is_custom:
            kind = controls.small(ANY_SERVER, palette)
        elif preset.needs_key:
            kind = controls.small(CLOUD, palette)
        else:
            # Plain wrapping text, not a pill: a pill cannot shrink and would widen the whole grid.
            kind = controls.small(LOCAL_BADGE, palette)
            kind.setStyleSheet(f"color: {style.css_color(style.success(palette))};")
        text.addWidget(kind)
        text.addStretch(1)
        line.addLayout(text, 1)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        border = style.accent(self._palette) if selected else style.hairline(self._palette)
        width = 2 if selected else style.HAIRLINE
        margin = 0 if selected else 1
        self.setStyleSheet(
            f"QFrame#{TILE_NAME} {{ background: {style.css_color(style.panel(self._palette))};"
            f"border: {width}px solid {style.css_color(border)}; border-radius: {style.CARD_RADIUS}px;"
            f"margin: {margin}px; }}"
        )

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
    """What the last connection test found: a light, one line, details and badges."""

    def __init__(self, palette: Any, action: QWidget):
        super().__init__()
        self._palette = palette
        self.setObjectName(STATUS_NAME)
        line = QHBoxLayout(self)
        line.setContentsMargins(*fields.FLAT_ROW_PADDING)
        line.setSpacing(12)
        self._light = QLabel()
        self._light.setFixedSize(LIGHT, LIGHT)
        line.addWidget(self._light, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.title = QLabel()
        self.title.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        text.addWidget(self.title)
        self.detail = controls.small("", palette)
        text.addWidget(self.detail)
        self._badges = QHBoxLayout()
        self._badges.setContentsMargins(0, 0, 0, 0)
        self._badges.setSpacing(6)
        self._badge_row = QWidget()
        self._badge_row.setLayout(self._badges)
        self._badges.addStretch(1)
        self._badge_widgets: list[QWidget] = []
        text.addWidget(self._badge_row)
        line.addLayout(text, 1)
        line.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.state = STATE_IDLE
        self.show_state(STATE_IDLE, "", "", [])

    def show_state(self, state: str, title: str, detail: str, badges: list[tuple[str, str]]) -> None:
        self.state = state
        colours = {
            STATE_OK: style.success(self._palette),
            STATE_BAD: style.danger(self._palette),
        }
        colour = colours.get(state, style.muted(self._palette))
        self._light.setStyleSheet(f"QLabel {{ background: {style.css_color(colour)}; border-radius: {LIGHT // 2}px; }}")
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        for widget in self._badge_widgets:
            self._badges.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self._badge_widgets = []
        for index, (text, kind) in enumerate(badges):
            widget = controls.badge(text, kind, self._palette)
            self._badges.insertWidget(index, widget)
            self._badge_widgets.append(widget)
        self._badge_row.setVisible(bool(badges))
