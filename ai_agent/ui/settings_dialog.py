from typing import Any

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import resolve
from ai_agent.core.llm.probe_worker import ProbeThread
from ai_agent.core.llm.providers import TITLES, by_title, matching
from ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    DEFAULT_API_URL,
    DEFAULT_TOKEN_BUDGET,
    GEOCODER_NOMINATIM,
    credential_store_failure_message,
    delete_api_key,
    get_allow_sensitive_data,
    get_api_key,
    get_api_url,
    get_credential_store_error,
    get_data_sharing_consent,
    get_model,
    get_verify_ssl,
    set_allow_sensitive_data,
    set_api_key,
    set_api_url,
    set_auth_type,
    set_custom_nominatim_url,
    set_data_sharing_consent,
    set_dialect,
    set_geocoder_provider,
    set_model,
    set_thinking_budget,
    set_token_budget,
    set_verify_after_apply,
    set_verify_ssl,
)
from ai_agent.i18n import tr
from ai_agent.ui import settings_advanced, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.geocoder_settings import GeocoderSettings
from ai_agent.ui.settings_status import SettingsStatusMixin

TITLE = tr("Settings — AI Agent")
MIN_WIDTH = 520
MARGINS = (16, 16, 16, 14)
SPACING = 12
SAVED = tr("Settings saved.")
TESTING = tr("Testing the connection…")
CANCELLING = tr("Cancelling the connection test…")
CANCELLED = tr("Connection test cancelled.")
MODEL_REQUIRED = tr("Enter a model name from the provider.")
KEY_REMOVED = tr("The stored key for this endpoint was removed.")
KEY_HINT = tr("Stored in the system keyring, not in the settings file.")
KEYLESS_HINT = tr("A local server needs no key — leave this empty.")
SHARING_LABEL = tr("Share project context with the model provider")
SHARING_HINT = tr(
    "Prompts and basic QGIS project context—including layer and field names, CRS, tool results and "
    "generated plans—may be sent to this endpoint. Consent is stored separately for every endpoint."
)
SENSITIVE_LABEL = tr("Allow sensitive GIS data and tool results")
SENSITIVE_HINT = tr(
    "Feature attribute values, exact map and layer extents, layer filters and sources, style categories, "
    "Processing and Python results, and rendered map or layout images may be sent to this endpoint. "
    "Leave this off for sensitive projects."
)
LOCAL_SHARING_HINT = tr(
    "Local endpoint: consent is implicit and sensitive tools are enabled. "
    "The server may still store or forward data; review its configuration."
)


class SettingsDialog(SettingsStatusMixin, QDialog):
    sharing_label = SHARING_LABEL
    sharing_hint = SHARING_HINT
    sensitive_label = SENSITIVE_LABEL
    sensitive_hint = SENSITIVE_HINT

    def __init__(self, parent: Any = None):
        super().__init__(parent)
        self._syncing_preset = False
        self._loading_endpoint = False
        self._active_credential_target: tuple[str, str] | None = None
        self._credential_drafts: dict[tuple[str, str], str] = {}
        self._probe_thread: ProbeThread | None = None
        self._probe_was_cancelled = False
        self._reject_after_probe = False
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(MIN_WIDTH)
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(*MARGINS)
        column.setSpacing(SPACING)
        column.addWidget(self._build_connection(palette))
        self.geocoder = GeocoderSettings(palette)
        column.addWidget(self.geocoder.widget)
        column.addWidget(settings_advanced.build(self, palette))
        self._status = fields.status(palette)
        column.addWidget(self._status)
        column.addStretch(1)
        column.addLayout(self._build_buttons(palette))
        self._sync_preset()
        self._load_endpoint_state(remember_current=False)

    def _build_connection(self, palette: Any) -> QWidget:
        frame, column = fields.card(palette)
        column.addWidget(fields.section(tr("Connection"), palette))

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(TITLES)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        column.addWidget(fields.field(tr("Provider"), self.preset_combo, "", palette))

        self.url_edit = QLineEdit(get_api_url())
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.textChanged.connect(self._sync_preset)
        self.url_edit.editingFinished.connect(self._endpoint_finished)
        column.addWidget(
            fields.field(tr("Base URL"), self.url_edit, tr("Without /chat/completions at the end."), palette)
        )

        self.model_edit = QLineEdit(get_model())
        column.addWidget(fields.field(tr("Model"), self.model_edit, "", palette))

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(tr("Provider key"))
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(self.key_edit, 1)
        self.remove_key_btn = QPushButton(tr("Remove stored key"))
        self.remove_key_btn.setStyleSheet(fields.plain_button(palette))
        self.remove_key_btn.clicked.connect(self._remove_key)
        key_layout.addWidget(self.remove_key_btn)
        self._key_field = fields.field(tr("API key"), key_row, KEY_HINT, palette)
        column.addWidget(self._key_field)
        return frame

    def _build_buttons(self, palette: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.test_btn = QPushButton(tr("Test connection"))
        self.test_btn.setStyleSheet(fields.plain_button(palette))
        self.test_btn.clicked.connect(self._test_connection)
        row.addWidget(self.test_btn)
        row.addStretch(1)

        close_btn = QPushButton(tr("Close"))
        close_btn.setStyleSheet(fields.plain_button(palette))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)

        save_btn = QPushButton(tr("Save"))
        save_btn.setStyleSheet(fields.accent_button(palette))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return row

    def _apply_preset(self, title: str) -> None:
        if self._syncing_preset:
            return
        preset = by_title(title)
        if preset.is_custom:
            self._paint_key_hint(True)
            return
        self._remember_key_draft()
        self._loading_endpoint = True
        try:
            self.url_edit.setText(preset.url)
            fields.select(self.dialect_combo, preset.dialect)
            fields.select(self.auth_type_combo, AUTH_TYPE_BEARER)
            self.model_edit.setText(preset.default_model)
        finally:
            self._loading_endpoint = False
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key)
        self._load_endpoint_state(remember_current=False)

    def _sync_preset(self) -> None:
        preset = matching(self.url_edit.text())
        self._syncing_preset = True
        try:
            fields.select(self.preset_combo, preset.title)
        finally:
            self._syncing_preset = False
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key or preset.is_custom)

    def _paint_key_hint(self, needs_key: bool) -> None:
        self._key_field.setToolTip(KEY_HINT if needs_key else KEYLESS_HINT)
        self.key_edit.setPlaceholderText(tr("Provider key") if needs_key else tr("Not required"))

    def _endpoint_finished(self, *_args: Any) -> None:
        if not self._loading_endpoint:
            self._load_endpoint_state()

    def _load_endpoint_state(self, remember_current: bool = True) -> None:
        if remember_current:
            self._remember_key_draft()
        url = self._edited_url()
        dialect = self.dialect_combo.currentText()
        target = self._credential_target(url, dialect)
        key = self._credential_drafts.get(target)
        if key is None:
            key = get_api_key(url, dialect)
        self.key_edit.setText(key)
        self._active_credential_target = target
        local = is_local(url)
        sharing_allowed = local or get_data_sharing_consent(url)
        sensitive_allowed = local or (sharing_allowed and get_allow_sensitive_data(url))
        self.data_sharing_cb.setChecked(sharing_allowed)
        self.sensitive_data_cb.setChecked(sensitive_allowed)
        self.data_sharing_cb.setEnabled(not local)
        self.sensitive_data_cb.setEnabled(not local and sharing_allowed)
        hint = LOCAL_SHARING_HINT if local else SHARING_HINT
        self.data_sharing_cb.setToolTip(hint)
        self.sensitive_data_cb.setToolTip(hint if local else SENSITIVE_HINT)
        self.verify_ssl_cb.setChecked(get_verify_ssl(url))
        if get_credential_store_error() and not is_local(url):
            self._show(credential_store_failure_message(), style.danger(self.palette()))
        else:
            self._show("", style.muted(self.palette()))

    def _remember_key_draft(self) -> None:
        if self._active_credential_target is not None:
            self._credential_drafts[self._active_credential_target] = self.key_edit.text()

    @staticmethod
    def _credential_target(url: str, dialect: str) -> tuple[str, str]:
        return url.strip().rstrip("/"), resolve(url, dialect)

    def _edited_url(self) -> str:
        return self.url_edit.text().strip() or DEFAULT_API_URL

    def _remove_key(self) -> None:
        url = self._edited_url()
        dialect = self.dialect_combo.currentText()
        try:
            delete_api_key(url, dialect)
        except RuntimeError as error:
            self._show(str(error), style.danger(self.palette()))
            return
        self.key_edit.clear()
        self._credential_drafts[self._credential_target(url, dialect)] = ""
        self._show(KEY_REMOVED, style.success(self.palette()))

    def _save(self) -> None:
        url = self._edited_url()
        if not self._valid_url(url):
            return
        try:
            geocoder_provider, geocoder_url = self.geocoder.values()
        except ValueError as error:
            self._show(str(error), style.danger(self.palette()))
            return
        dialect = self.dialect_combo.currentText()
        model = self.model_edit.text().strip()
        if not model:
            self._show(MODEL_REQUIRED, style.danger(self.palette()))
            return
        set_api_url(url)
        set_model(model)
        set_auth_type(self.auth_type_combo.currentText())
        set_dialect(dialect)
        set_verify_ssl(self.verify_ssl_cb.isChecked(), url)
        set_data_sharing_consent(self.data_sharing_cb.isChecked(), url)
        sensitive_allowed = self.data_sharing_cb.isChecked() and self.sensitive_data_cb.isChecked()
        set_allow_sensitive_data(sensitive_allowed, url)
        set_verify_after_apply(self.verify_apply_cb.isChecked())
        set_token_budget(fields.parsed_budget(self.budget_edit.text(), DEFAULT_TOKEN_BUDGET))
        set_thinking_budget(fields.parsed_budget(self.thinking_edit.text(), DEFAULT_TOKEN_BUDGET))
        set_geocoder_provider(geocoder_provider)
        if geocoder_provider == GEOCODER_NOMINATIM:
            set_custom_nominatim_url(geocoder_url)
        key = self.key_edit.text()
        if key:
            try:
                set_api_key(key, url, dialect)
            except RuntimeError as error:
                self._show(str(error), style.danger(self.palette()))
                return
        self._show(SAVED, style.success(self.palette()))

    def _test_connection(self) -> None:
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._cancel_probe()
            return
        if not self.model_edit.text().strip():
            self._show(MODEL_REQUIRED, style.danger(self.palette()))
            return
        if not self._valid_url(self._edited_url()):
            return
        self.test_btn.setText(tr("Cancel test"))
        self._show(TESTING, style.muted(self.palette()))
        self._probe_was_cancelled = False
        thread = ProbeThread(self._overrides(), self)
        thread.completed.connect(self._on_probe_completed)
        thread.finished.connect(lambda: self._on_probe_finished(thread))
        self._probe_thread = thread
        thread.start()

    def _on_probe_completed(self, ok: bool, message: str) -> None:
        palette = self.palette()
        self._show(message, style.success(palette) if ok else style.danger(palette))

    def _on_probe_finished(self, thread: ProbeThread) -> None:
        thread.deleteLater()
        if self._probe_thread is not thread:
            return
        cancelled = self._probe_was_cancelled
        close_dialog = self._reject_after_probe
        self._probe_thread = None
        self._probe_was_cancelled = False
        self._reject_after_probe = False
        self.test_btn.setEnabled(True)
        self.test_btn.setText(tr("Test connection"))
        if close_dialog:
            super().reject()
        elif cancelled:
            self._show(CANCELLED, style.muted(self.palette()))

    def _cancel_probe(self) -> None:
        thread = self._probe_thread
        if thread is None or not thread.isRunning():
            return
        self._probe_was_cancelled = True
        thread.cancel()
        self.test_btn.setEnabled(False)
        self._show(CANCELLING, style.muted(self.palette()))

    def reject(self) -> None:
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._reject_after_probe = True
            self._cancel_probe()
            return
        self._cancel_probe()
        super().reject()

    def _overrides(self) -> dict[str, Any]:
        url = self._edited_url()
        dialect = self.dialect_combo.currentText()
        return {
            "url_override": url,
            "model_override": self.model_edit.text().strip() or None,
            "key_override": self.key_edit.text().strip() or get_api_key(url, dialect) or None,
            "auth_type_override": self.auth_type_combo.currentText() or None,
            "dialect_override": dialect or None,
            "verify_override": self.verify_ssl_cb.isChecked(),
        }
