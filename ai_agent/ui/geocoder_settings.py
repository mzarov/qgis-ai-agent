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

PHOTON_HINT = tr(
    "Photon's public demo permits reasonable use, may throttle heavy traffic and has no availability guarantee."
)
CUSTOM_HINT = tr("Use a public HTTPS Nominatim-compatible service whose operator permits your intended use.")
DISABLED_HINT = tr("Geocoding stays unavailable until you select a service.")
PURPOSE_HINT = tr(
    'With a geocoder the agent can turn "cafes in Divnomorskoye" into a bounding box and hand it to the '
    "OpenStreetMap download. Without one it can still work by place name, but only where OpenStreetMap "
    "already knows that name."
)


class GeocoderSettings:
    def __init__(self, palette: Any):
        self._palette = palette
        self._custom_url = get_custom_nominatim_url()
        self._last_provider = get_geocoder_provider()
        holder, column = fields.page()
        fields.section(column, tr("Service"), palette, PURPOSE_HINT)
        self.provider_combo = controls.RadioCards(palette)
        self.provider_combo.addItem(tr("Disabled"), GEOCODER_DISABLED, DISABLED_HINT)
        self.provider_combo.addItem(tr("Photon demo (fair use)"), GEOCODER_PHOTON, PHOTON_HINT)
        custom = self.provider_combo.addItem(tr("Custom Nominatim"), GEOCODER_NOMINATIM, CUSTOM_HINT)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://geocoder.example")
        self.url_edit.setStyleSheet(fields.input_style(palette))
        custom.add_extra(self.url_edit)
        index = self.provider_combo.findData(self._last_provider)
        self.provider_combo.setCurrentIndex(max(0, index))
        column.addWidget(self.provider_combo)
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
        # The address belongs to the custom service only; it stays visible but idle otherwise.
        self.url_edit.setText(self._custom_url)
        self.url_edit.setEnabled(provider == GEOCODER_NOMINATIM)
