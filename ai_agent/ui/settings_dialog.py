from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.core.connectors import save_enabled
from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import resolve
from ai_agent.core.llm.probe_worker import ProbeThread
from ai_agent.core.llm.providers import PRESETS, TITLES, by_title, matching
from ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    DEFAULT_API_URL,
    GEOCODER_NOMINATIM,
    credential_store_failure_message,
    delete_api_key,
    get_api_key,
    get_api_url,
    get_credential_store_error,
    get_model,
    get_verify_ssl,
    set_api_key,
    set_api_url,
    set_auth_type,
    set_context_window,
    set_custom_nominatim_url,
    set_dialect,
    set_geocoder_provider,
    set_model,
    set_reasoning_enabled,
    set_thinking_budget,
    set_token_budget,
    set_verify_after_apply,
    set_verify_ssl,
    set_write_run_journal,
)
from ai_agent.i18n import tr
from ai_agent.ui import controls, settings_layout, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.connection_widgets import ProviderTiles, StatusCard
from ai_agent.ui.connectors_settings import ConnectorsSettings
from ai_agent.ui.geocoder_settings import GeocoderSettings
from ai_agent.ui.personalisation_settings import PersonalisationSettings
from ai_agent.ui.settings_probe import MODEL_REQUIRED, ConnectionProbeMixin
from ai_agent.ui.settings_status import SettingsStatusMixin
from ai_agent.ui.skills_settings import SkillsSettings

TITLE = tr("Settings — AI Agent")
MIN_WIDTH = 860
MIN_HEIGHT = 600
FOOTER_MARGINS = (24, 12, 24, 12)
FOOTER_SPACING = 8
CONNECTION_LEAD = tr("Any OpenAI-compatible server works.")
SAVED = tr("All changes saved")
UNSAVED = tr("Unsaved changes")
BUDGET_INVALID = tr("A budget must be a whole number of tokens, such as 200000 or 200k; empty means no limit.")
KEY_REMOVED = tr("The stored key for this endpoint was removed.")
KEY_HINT = tr("Kept in the QGIS authentication database.")
KEYLESS_HINT = tr("A local server needs no key.")
MODEL_HINT = tr("As the provider names it.")


class SettingsDialog(ConnectionProbeMixin, SettingsStatusMixin, QDialog):
    def __init__(self, parent: Any = None):
        super().__init__(parent)
        style.apply_palette(self)
        self._syncing_preset = False
        self._loading_endpoint = False
        self._active_credential_target: tuple[str, str] | None = None
        self._credential_drafts: dict[tuple[str, str], str] = {}
        self._probe_thread: ProbeThread | None = None
        self._probe_was_cancelled = False
        self._reject_after_probe = False
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(MIN_WIDTH)
        self.setMinimumHeight(MIN_HEIGHT)
        self._probe_started = 0.0
        # An example request picked on a connector page, for the chat box once the dialog closes.
        self.chosen_prompt = ""
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.geocoder = GeocoderSettings(palette)
        self.skills = SkillsSettings(palette)
        self.connectors = ConnectorsSettings(palette)
        self.connectors.prompt_chosen.connect(self._use_example)
        self.connectors.page_switched.connect(lambda: self.pages.currentWidget().verticalScrollBar().setValue(0))
        self.personalisation = PersonalisationSettings(palette)
        body, right = settings_layout.build_body(self, palette)
        column.addLayout(body, 1)
        right.addWidget(fields.separator(palette))
        footer = QHBoxLayout()
        footer.setContentsMargins(*FOOTER_MARGINS)
        footer.setSpacing(FOOTER_SPACING)
        self._status = fields.status(palette)
        self._note = controls.small(SAVED, palette)
        self._note.setWordWrap(False)
        footer.addWidget(self._status, 1)
        footer.addWidget(self._note, 1)
        footer.addLayout(self._build_buttons(palette))
        right.addLayout(footer)
        self._sync_preset()
        self._load_endpoint_state(remember_current=False)
        self._show_untested()
        self._watch_changes()

    def _build_connection(self, palette: Any) -> QWidget:
        holder, column = fields.page()
        self.test_btn = QPushButton(tr("Test connection"))
        self.test_btn.setStyleSheet(fields.plain_button(palette))
        self.test_btn.clicked.connect(self._test_connection)
        self.status_card = StatusCard(palette, self.test_btn)

        fields.section(column, tr("Provider"), palette, CONNECTION_LEAD)
        # The combo box stays the single source of truth for the preset; the tiles only draw it.
        self.preset_combo = QComboBox(holder)
        self.preset_combo.addItems(TITLES)
        self.preset_combo.hide()
        self.provider_tiles = ProviderTiles(PRESETS, palette)
        self.provider_tiles.chosen.connect(self.preset_combo.setCurrentText)
        self.preset_combo.currentTextChanged.connect(self.provider_tiles.select)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        column.addWidget(self.provider_tiles)

        fields.section(column, tr("Endpoint"), palette)
        self.url_edit = QLineEdit(get_api_url())
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.textChanged.connect(self._sync_preset)
        self.url_edit.editingFinished.connect(self._endpoint_finished)
        self.model_edit = QLineEdit(get_model())

        key_box = QWidget()
        key_column = QVBoxLayout(key_box)
        key_column.setContentsMargins(0, 0, 0, 0)
        key_column.setSpacing(6)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(tr("Provider key"))
        key_column.addWidget(self.key_edit)
        self.remove_key_btn = QPushButton(tr("Remove key"))
        self.remove_key_btn.setStyleSheet(fields.ghost_button(palette))
        self.remove_key_btn.clicked.connect(self._remove_key)
        key_column.addWidget(self.remove_key_btn, 0, Qt.AlignmentFlag.AlignRight)
        self._key_field = fields.row(tr("API key"), key_box, KEY_HINT, palette)
        self._model_field = fields.row(tr("Model"), self.model_edit, MODEL_HINT, palette)
        column.addWidget(
            fields.card_rows(
                palette,
                [
                    fields.row(tr("Base URL"), self.url_edit, tr("Without /chat/completions."), palette),
                    self._model_field,
                    self._key_field,
                    self.status_card,
                ],
            )
        )
        column.addStretch(1)
        return holder

    def _build_buttons(self, palette: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        close_btn = QPushButton(tr("Cancel"))
        close_btn.setStyleSheet(fields.ghost_button(palette))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        self.save_btn = QPushButton(tr("Save"))
        self.save_btn.setStyleSheet(fields.accent_button(palette))
        self.save_btn.setDefault(True)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        row.addWidget(self.save_btn)
        return row

    def _watch_changes(self) -> None:
        """Mark a page as edited the moment one of its controls changes; Save waits for that."""
        pages = {
            0: [
                self.preset_combo.currentTextChanged,
                self.url_edit.textEdited,
                self.model_edit.textEdited,
                self.key_edit.textEdited,
            ],
            1: [self.verify_ssl_cb.toggled, self.journal_cb.toggled],
            3: [self.geocoder.provider_combo.currentIndexChanged, self.geocoder.url_edit.textEdited],
            4: [
                self.verify_apply_cb.toggled,
                self.budget_edit.textChanged,
                self.reasoning_cb.toggled,
                self.thinking_edit.textEdited,
                self.context_edit.textEdited,
                self.dialect_combo.currentTextChanged,
                self.auth_type_combo.currentTextChanged,
            ],
            5: [self.connectors.changed],
            6: [self.personalisation.changed],
        }
        for index, signals in pages.items():
            for signal in signals:
                signal.connect(lambda *_args, at=index: self._mark_dirty(at))

    def _mark_dirty(self, index: int) -> None:
        if self._loading_endpoint:
            return
        settings_layout.mark_page(self, index)
        self.save_btn.setEnabled(True)
        if self._note.text() != UNSAVED:
            self._note.setText(UNSAVED)
            self._note.setStyleSheet(f"color: {style.css_color(style.warning(self.palette()))};")

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
        # The combo only signals a change; the custom preset is its first item, so redraw the tiles directly.
        self.provider_tiles.select(preset.title)
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key or preset.is_custom)

    def _paint_key_hint(self, needs_key: bool) -> None:
        fields.set_row_hint(self._key_field, KEY_HINT if needs_key else KEYLESS_HINT)
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

    def _use_example(self, identifier: str, text: str) -> None:
        """Close with the request for the chat box, turning its connector on and saving, as asking means using it."""
        self.connectors.switches[identifier].setChecked(True)
        self.chosen_prompt = text
        if self.save_btn.isEnabled():
            self._save()
        else:
            self.accept()

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
        token_budget = fields.parsed_budget(self.budget_edit.text())
        thinking_budget = fields.parsed_budget(self.thinking_edit.text())
        context_window = fields.parsed_budget(self.context_edit.text())
        if token_budget is None or thinking_budget is None or context_window is None:
            self._show(BUDGET_INVALID, style.danger(self.palette()))
            return
        set_api_url(url)
        set_model(model)
        set_auth_type(self.auth_type_combo.currentText())
        set_dialect(dialect)
        set_verify_ssl(self.verify_ssl_cb.isChecked(), url)
        set_verify_after_apply(self.verify_apply_cb.isChecked())
        set_write_run_journal(self.journal_cb.isChecked())
        set_token_budget(token_budget)
        set_thinking_budget(thinking_budget)
        set_context_window(context_window)
        set_reasoning_enabled(self.reasoning_cb.isChecked(), url, model, dialect)
        set_geocoder_provider(geocoder_provider)
        save_enabled(self.connectors.enabled_ids())
        try:
            self.personalisation.save()
        except ValueError as error:
            self._show(str(error), style.danger(self.palette()))
            return
        if geocoder_provider == GEOCODER_NOMINATIM:
            set_custom_nominatim_url(geocoder_url)
        key = self.key_edit.text()
        if key:
            try:
                set_api_key(key, url, dialect)
            except RuntimeError as error:
                self._show(str(error), style.danger(self.palette()))
                return
        self._stop_probe_now()
        self.accept()

    def _overrides(self) -> dict[str, Any]:
        url = self._edited_url()
        dialect = self.dialect_combo.currentText()
        return {
            "url_override": url,
            "model_override": self.model_edit.text().strip() or None,
            "key_override": self.key_edit.text().strip() or get_api_key(url, dialect) or "",
            "auth_type_override": self.auth_type_combo.currentText() or None,
            "dialect_override": dialect or None,
            "verify_override": self.verify_ssl_cb.isChecked(),
        }
