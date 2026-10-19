from typing import Any

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from ai_agent.config.geocoder import validated_service_url
from ai_agent.core.settings import (
    GEOCODER_DISABLED,
    GEOCODER_NOMINATIM,
    GEOCODER_PHOTON,
    GEOCODER_PHOTON_URL,
    get_custom_nominatim_url,
    get_geocoder_provider,
)
from ai_agent.i18n import tr
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.choice_tiles import ChoiceTile, TileGrid

TITLE = tr("Geocoding")
LEAD = tr("Turns place names into coordinates, as when you ask for schools in Kazan.")
SERVICE = tr("Service")
PARAMETERS = tr("Parameters")
ADDRESS = tr("Server address")
PUBLIC_NOTE = tr("A public server")
OWN_NOTE = tr("Your Nominatim")
CHOICES = (
    (GEOCODER_DISABLED, tr("Turned off"), tr("The agent asks for coordinates or a selection on the map")),
    (GEOCODER_PHOTON, "Photon", tr("No key, for occasional lookups; forgives typos")),
    (GEOCODER_NOMINATIM, tr("Your own server"), tr("A Nominatim on your network, or a public one you may use")),
)
TILE_WIDTH = 180
MAX_COLUMNS = 3


class GeocoderSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        self._custom_url = get_custom_nominatim_url()
        self._provider = get_geocoder_provider()
        holder, column = fields.page(TITLE, LEAD, palette)
        fields.section(column, SERVICE, palette)
        column.addSpacing(fields.WIDE_GAP)
        self.tiles = TileGrid(
            [ChoiceTile(key, title, note, palette) for key, title, note in CHOICES], TILE_WIDTH, MAX_COLUMNS
        )
        self.tiles.chosen.connect(self._choose)
        column.addWidget(self.tiles)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://nominatim.example.org")
        self.url_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.url_edit.textEdited.connect(lambda _text: self.changed.emit())
        self._url_row = fields.row(ADDRESS, self.url_edit, "", palette)
        self._parameters = QWidget()
        parameters = QVBoxLayout(self._parameters)
        parameters.setContentsMargins(0, 0, 0, 0)
        parameters.setSpacing(0)
        fields.section(parameters, PARAMETERS, palette)
        parameters.addWidget(self._url_row)
        column.addSpacing(fields.SECTION_GAP)
        column.addWidget(self._parameters)
        column.addStretch(1)
        self._show(self._provider)
        self.widget: QWidget = holder

    def values(self) -> tuple[str, str]:
        provider = self._provider
        if provider == GEOCODER_DISABLED:
            return provider, self._custom_url
        if provider == GEOCODER_PHOTON:
            return provider, GEOCODER_PHOTON_URL
        return provider, validated_service_url(self.url_edit.text())

    def _choose(self, provider: str) -> None:
        if provider == self._provider:
            return
        if self._provider == GEOCODER_NOMINATIM:
            self._custom_url = self.url_edit.text().strip()
        self._provider = provider
        self._show(provider)
        self.changed.emit()

    def _show(self, provider: str) -> None:
        self.tiles.select(provider)
        self._parameters.setVisible(provider != GEOCODER_DISABLED)
        own = provider == GEOCODER_NOMINATIM
        self.url_edit.setText(self._custom_url if own else GEOCODER_PHOTON_URL)
        self.url_edit.setEnabled(own)
        fields.set_row_hint(self._url_row, OWN_NOTE if own else PUBLIC_NOTE)
