from typing import Any

from qgis.PyQt.QtWidgets import QLineEdit, QWidget

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
from ai_agent.ui import controls
from ai_agent.ui import settings_fields as fields

PURPOSE_HINT = tr("Turns place names into coordinates for OpenStreetMap downloads.")
DISABLED_HINT = tr("Only names OpenStreetMap already knows will be found.")
PHOTON_HINT = tr("Free public demo, fine for occasional lookups.")
CUSTOM_HINT = tr("Your own server, or a public one that allows your use.")
HINTS = {GEOCODER_DISABLED: DISABLED_HINT, GEOCODER_PHOTON: PHOTON_HINT, GEOCODER_NOMINATIM: CUSTOM_HINT}


class GeocoderSettings:
    def __init__(self, palette: Any):
        self._palette = palette
        self._custom_url = get_custom_nominatim_url()
        self._last_provider = get_geocoder_provider()
        holder, column = fields.page()
        fields.section(column, tr("Geocoding"), palette, PURPOSE_HINT)
        self.provider_combo = controls.Segmented(palette)
        self.provider_combo.addItem(tr("Off"), GEOCODER_DISABLED)
        self.provider_combo.addItem("Photon", GEOCODER_PHOTON)
        self.provider_combo.addItem("Nominatim", GEOCODER_NOMINATIM)
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(self._last_provider)))
        self._service_row = fields.custom_row(tr("Service"), self.provider_combo, "", palette)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://nominatim.example.org")
        # The address row carries its own hairline, so hiding it leaves no stray line behind.
        self._url_row = fields.card_rows(
            palette, [QWidget(), fields.row(tr("Server address"), self.url_edit, "", palette)]
        )
        column.addWidget(self._service_row)
        column.addWidget(self._url_row)
        column.addStretch(1)
        self.provider_combo.currentIndexChanged.connect(self._sync_provider)
        self._sync_provider()
        self.widget: QWidget = holder

    def values(self) -> tuple[str, str]:
        provider = self._provider()
        if provider == GEOCODER_DISABLED:
            return provider, self._custom_url
        if provider == GEOCODER_PHOTON:
            return provider, GEOCODER_PHOTON_URL
        url = validated_service_url(self.url_edit.text())
        return provider, url

    def _provider(self) -> str:
        provider = str(self.provider_combo.currentData() or "")
        allowed = {GEOCODER_DISABLED, GEOCODER_PHOTON, GEOCODER_NOMINATIM}
        return provider if provider in allowed else GEOCODER_DISABLED

    def _sync_provider(self, *_args: Any) -> None:
        provider = self._provider()
        if self._last_provider == GEOCODER_NOMINATIM:
            self._custom_url = self.url_edit.text().strip()
        self._last_provider = provider
        self.url_edit.setText(self._custom_url)
        fields.set_row_hint(self._service_row, HINTS[provider])
        # The address belongs to the custom server only: the row shows up when it is chosen.
        self._url_row.setVisible(provider == GEOCODER_NOMINATIM)
