from typing import Any

from qgis.PyQt.QtWidgets import QComboBox, QLineEdit, QWidget

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
        column.addWidget(fields.group(tr("Turning a place name into coordinates"), palette))
        column.addWidget(fields.hint(PURPOSE_HINT, palette))
        column.addSpacing(fields.GROUP_GAP)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(tr("Disabled"), GEOCODER_DISABLED)
        self.provider_combo.addItem(tr("Photon demo (fair use)"), GEOCODER_PHOTON)
        self.provider_combo.addItem(tr("Custom Nominatim"), GEOCODER_NOMINATIM)
        index = self.provider_combo.findData(self._last_provider)
        self.provider_combo.setCurrentIndex(max(0, index))
        self.url_edit = QLineEdit()
        self.url_field = fields.row(tr("Base URL"), self.url_edit, DISABLED_HINT, palette)
        fields.add_rows(
            column,
            palette,
            [
                fields.row(tr("Service"), self.provider_combo, "", palette),
                self.url_field,
            ],
        )
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
        if provider == GEOCODER_PHOTON:
            self.url_edit.setText(GEOCODER_PHOTON_URL)
            hint = PHOTON_HINT
        elif provider == GEOCODER_NOMINATIM:
            self.url_edit.setText(self._custom_url)
            hint = CUSTOM_HINT
        else:
            self.url_edit.clear()
            hint = DISABLED_HINT
        self.url_edit.setReadOnly(provider != GEOCODER_NOMINATIM)
        self.url_edit.setPlaceholderText("https://geocoder.example")
        self.url_edit.setToolTip(hint)
        self.url_field.setToolTip(hint)
        if self.url_field.help is not None:
            self.url_field.help.setToolTip(hint)
