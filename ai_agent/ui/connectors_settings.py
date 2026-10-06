"""The Connectors page: the open-data sources the agent may use, as cards with a switch each.

Cards in a grid like the Connection page's provider tiles: a monogram (country
code for national services), the name, what it offers and how many datasets,
and a switch; a switched-off card dims. Chips pick a group, the search box
narrows by name and description. Nothing here goes online.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.connectors import categories, connector_rows
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

TITLE = tr("Connectors")
INTRO = tr(
    "Where the agent gets data you do not have: ask for a satellite picture, boundaries or an aerial "
    "photo and it loads them from these sources. A source you switch off is hidden from it."
)
SEARCH = tr("Search connectors")
NOTHING = tr("No connector matches.")
ALL = tr("All")
CARD_NAME = "connectorCard"
CARD_MIN_WIDTH = 280
CARD_GAP = 12
# The page had everything touching: the search, the chips, a group title and its cards each get air.
INTRO_TO_SEARCH = 14
SEARCH_TO_CHIPS = 12
GROUP_GAP = 28
TITLE_TO_CARDS = 12
CARD_HEIGHT = 72
MAX_COLUMNS = 2
MONOGRAM = 34
MONOGRAM_RADIUS = 8
MONOGRAM_SCALE = 0.85
GLYPH = 17
# Country codes for national services; the rest wear the globe.
MONOGRAMS = {"ign-france": "FR", "pdok": "NL", "swisstopo": "CH", "usgs": "US", "ga-australia": "AU"}
GLYPHS = {"openstreetmap": "geocoding", "geoboundaries": "geocoding"}
# What a person reads about each source; the catalogue's English summaries are written for the model.
SUMMARIES = {
    "openstreetmap": tr("Roads, buildings and places by tag, worldwide"),
    "natural-earth": tr("Small tidy world layers: countries, rivers, cities"),
    "opentopomap": tr("Topographic world map with contours"),
    "planetary-computer": tr("Sentinel-2, Landsat, elevation and land cover scenes"),
    "nasa-gibs": tr("Yesterday's Earth from space, night lights, Blue Marble"),
    "eox": tr("Cloud-free satellite mosaic of the world, non-commercial use"),
    "gebco": tr("Ocean depths and land heights"),
    "geoboundaries": tr("Administrative boundaries of every country"),
    "ign-france": tr("France: aerial photos, maps, communes"),
    "pdok": tr("Netherlands: aerial photos, base map, municipalities"),
    "swisstopo": tr("Switzerland: national map and aerial photos"),
    "usgs": tr("United States: aerial imagery and US Topo"),
    "ga-australia": tr("Australia: topographic base maps"),
}
# Chips need short words: the full group titles in a row did not fit the page in Russian.
CHIP_TITLES = {
    "world": tr("World"),
    "imagery": tr("Imagery"),
    "terrain": tr("Terrain"),
    "people": tr("Places"),
    "national": tr("National"),
}
CATEGORY_TITLES = {
    "world": tr("Worldwide maps"),
    "imagery": tr("Satellites and imagery"),
    "terrain": tr("Terrain and oceans"),
    "people": tr("Places and boundaries"),
    "national": tr("National mapping"),
}


class ConnectorCard(controls.RoundedFrame):
    """One source: monogram, name and count, what it offers, a switch; dimmed while off."""

    def __init__(self, row: dict[str, Any], palette: Any):
        super().__init__(style.CARD_RADIUS)
        self.identifier = str(row["id"])
        # Kept apart from isHidden(): a card not yet laid out reports hidden and would never be placed.
        self.matched = True
        self.category = str(row["category"])
        self._palette = palette
        self.setObjectName(CARD_NAME)
        self.setMinimumHeight(CARD_HEIGHT)
        summary = SUMMARIES.get(self.identifier, str(row["summary"]))
        self.haystack = " ".join((str(row["title"]), str(row["summary"]), summary)).lower()
        line = QHBoxLayout(self)
        line.setContentsMargins(14, 12, 14, 12)
        line.setSpacing(12)
        line.addWidget(_monogram(self.identifier, palette), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.name = controls.ElidedLabel(str(row["title"]))
        text.addWidget(self.name)
        # The count rides with the summary: beside the name it squeezed names to an ellipsis in two columns.
        summary = f"{summary} · {tr_n('%n dataset(s)', int(row['count']))}"
        self.summary = controls.small(summary, palette)
        self.summary.setToolTip(", ".join(row["hosts"]))
        text.addWidget(self.summary)
        line.addLayout(text, 1)
        self.switch = fields.switch(palette)
        self.switch.setChecked(bool(row["enabled"]))
        self.switch.toggled.connect(self._shade)
        line.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        self._shade(self.switch.isChecked())

    def _shade(self, enabled: bool) -> None:
        palette = self._palette
        style.ink(self.name, style.text(palette) if enabled else style.faint(palette))
        self.set_look(style.panel(palette).name(), style.hairline(palette).name())


class ConnectorsSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        holder, column = fields.page()
        fields.section(column, TITLE, palette, INTRO)
        column.addSpacing(INTRO_TO_SEARCH)
        self.search = QLineEdit()
        self.search.setPlaceholderText(SEARCH)
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(fields.input_style(palette))
        self.search.textChanged.connect(self._filter)
        column.addWidget(self.search)
        self._category = ""
        column.addSpacing(SEARCH_TO_CHIPS)
        column.addWidget(self._chips(palette))
        self.cards: list[ConnectorCard] = []
        self._groups: list[tuple[QLabel, QWidget, list[ConnectorCard]]] = []
        rows = connector_rows()
        for category in categories():
            members = [ConnectorCard(row, palette) for row in rows if row["category"] == category]
            if not members:
                continue
            for card in members:
                card.switch.toggled.connect(lambda _on: self.changed.emit())
            title = fields.heading(CATEGORY_TITLES.get(category, category), palette)
            column.addSpacing(GROUP_GAP)
            column.addWidget(title)
            column.addSpacing(TITLE_TO_CARDS)
            grid = CardGrid(members)
            column.addWidget(grid)
            self.cards.extend(members)
            self._groups.append((title, grid, members))
        self._empty = fields.hint(NOTHING, palette)
        self._empty.setVisible(False)
        column.addWidget(self._empty)
        column.addStretch(1)
        self.widget = holder

    @property
    def switches(self) -> dict[str, Any]:
        return {card.identifier: card.switch for card in self.cards}

    def enabled_ids(self) -> list[str]:
        return [card.identifier for card in self.cards if card.switch.isChecked()]

    def _chips(self, palette: Any) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.chips: list[tuple[QPushButton, str]] = []
        for key, label in (("", ALL), *((key, CHIP_TITLES.get(key, key)) for key in categories())):
            chip = QPushButton(label)
            chip.setCheckable(True)
            chip.setChecked(key == "")
            chip.setFixedHeight(controls.CHIP_HEIGHT)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(controls.chip_style(palette))
            chip.clicked.connect(lambda _checked=False, chosen=key: self._choose(chosen))
            line.addWidget(chip)
            self.chips.append((chip, key))
        line.addStretch(1)
        return holder

    def _choose(self, category: str) -> None:
        self._category = category
        for chip, key in self.chips:
            chip.setChecked(key == category)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        shown = 0
        for title, grid, members in self._groups:
            in_group = 0
            for card in members:
                match = (not self._category or card.category == self._category) and all(
                    word in card.haystack for word in words
                )
                card.matched = bool(match)
                card.setVisible(match)
                in_group += match
            title.setVisible(bool(in_group))
            grid.setVisible(bool(in_group))
            grid.rearrange()
            shown += in_group
        self._empty.setVisible(shown == 0)


class CardGrid(QWidget):
    """Cards two to a row when they fit, one when the window is narrow; hidden cards leave no gap."""

    def __init__(self, cards: list[ConnectorCard]):
        super().__init__()
        self._cards = cards
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(CARD_GAP)
        self._columns = MAX_COLUMNS
        self.rearrange()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        fits = max(1, min(MAX_COLUMNS, (self.width() + CARD_GAP) // (CARD_MIN_WIDTH + CARD_GAP)))
        if fits != self._columns:
            self._columns = fits
            self.rearrange()

    def rearrange(self) -> None:
        for card in self._cards:
            self._grid.removeWidget(card)
        for column in range(MAX_COLUMNS):
            self._grid.setColumnStretch(column, 1 if column < self._columns else 0)
        visible = [card for card in self._cards if card.matched]
        for index, card in enumerate(visible):
            self._grid.addWidget(card, index // self._columns, index % self._columns)


def _monogram(identifier: str, palette: Any) -> QLabel:
    label = QLabel()
    label.setFixedSize(MONOGRAM, MONOGRAM)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.accent_ink(palette))}; border-radius: {MONOGRAM_RADIUS}px; }}"
    )
    code = MONOGRAMS.get(identifier)
    icon = None if code else icons.drawn(GLYPHS.get(identifier, "connectors"), style.accent(palette), GLYPH)
    if icon is not None:
        label.setPixmap(icon.pixmap(GLYPH, GLYPH))
    else:
        style.scale_font(label, MONOGRAM_SCALE, bold=True)
        label.setText(code or identifier[:2].upper())
    return label
