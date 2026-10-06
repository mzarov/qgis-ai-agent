"""The Connectors page: the open-data sources the agent may use, each with a switch.

Grouped by kind, with a search over names and descriptions. A source switched
off disappears from the agent's catalogue; nothing here goes online.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QLineEdit, QWidget

from ai_agent.core.connectors import categories, connector_rows
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import settings_fields as fields

TITLE = tr("Connectors")
INTRO = tr("Open data sources the agent can fetch from. A source you switch off is hidden from it.")
SEARCH = tr("Search connectors")
NOTHING = tr("No connector matches.")
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
CATEGORY_TITLES = {
    "world": tr("Worldwide maps"),
    "imagery": tr("Satellites and imagery"),
    "terrain": tr("Terrain and oceans"),
    "people": tr("Places and boundaries"),
    "national": tr("National mapping"),
}


class ConnectorsSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        holder, column = fields.page()
        fields.section(column, TITLE, palette, INTRO)
        self.search = QLineEdit()
        self.search.setPlaceholderText(SEARCH)
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(fields.input_style(palette))
        self.search.textChanged.connect(self._filter)
        column.addWidget(self.search)
        self.switches: dict[str, Any] = {}
        self._rows: list[tuple[QWidget, str]] = []
        self._groups: list[tuple[QWidget, QWidget, list[QWidget]]] = []
        rows = connector_rows()
        for category in categories():
            members = [row for row in rows if row["category"] == category]
            if not members:
                continue
            title = fields.heading(CATEGORY_TITLES.get(category, category), palette)
            column.addSpacing(fields.SECTION_TO_CARD)
            column.addWidget(title)
            built = [self._row(row, palette) for row in members]
            card = fields.card_rows(palette, built)
            column.addWidget(card)
            self._groups.append((title, card, built))
        self._empty = fields.hint(NOTHING, palette)
        self._empty.setVisible(False)
        column.addWidget(self._empty)
        column.addStretch(1)
        self.widget = holder

    def _row(self, row: dict[str, Any], palette: Any) -> QWidget:
        switch = fields.switch(palette)
        switch.setChecked(bool(row["enabled"]))
        switch.toggled.connect(lambda _on: self.changed.emit())
        self.switches[row["id"]] = switch
        summary = SUMMARIES.get(row["id"], row["summary"])
        note = f"{summary} · {tr_n('%n dataset(s)', int(row['count']))}"
        built = fields.switch_row(row["title"], switch, note, palette, ", ".join(row["hosts"]))
        self._rows.append((built, " ".join((row["title"], row["summary"], summary)).lower()))
        return built

    def enabled_ids(self) -> list[str]:
        return [identifier for identifier, switch in self.switches.items() if switch.isChecked()]

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        shown = set()
        for built, haystack in self._rows:
            match = all(word in haystack for word in words)
            built.setVisible(match)
            if match:
                shown.add(built)
        for title, card, built_rows in self._groups:
            has_match = any(built in shown for built in built_rows)
            title.setVisible(has_match)
            card.setVisible(has_match)
        self._empty.setVisible(not shown)
