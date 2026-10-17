from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFontDatabase
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
from ai_agent.core.llm.dialects import AUTO, resolve
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
    set_disabled_skills,
    set_geocoder_provider,
    set_model,
    set_reasoning_enabled,
    set_thinking_budget,
    set_token_budget,
    set_verify_after_apply,
    set_verify_ssl,
    set_write_run_journal,
)
from ai_agent.core.usage_stats import save_usage_choice
from ai_agent.i18n import tr
from ai_agent.ui import controls, settings_advanced, settings_layout, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.connection_widgets import ProviderTiles, StatusCard
from ai_agent.ui.connectors_settings import ConnectorsSettings
from ai_agent.ui.geocoder_settings import GeocoderSettings
from ai_agent.ui.personalisation_settings import PersonalisationSettings
from ai_agent.ui.settings_probe import MODEL_REQUIRED, ConnectionProbeMixin
from ai_agent.ui.settings_status import SettingsStatusMixin
from ai_agent.ui.skills_settings import SkillsSettings

TITLE = tr("Settings — AI Agent")
MIN_WIDTH = 920
MIN_HEIGHT = 640
FOOTER_MARGINS = (28, 11, 16, 11)
FOOTER_SPACING = 8
FOOTER_DOT = 6
CONNECTION_TITLE = tr("Connection")
CONNECTION_LEAD = tr(
    "Any OpenAI-compatible server works. Keys are kept in the QGIS authentication database, not in the project."
)
CUSTOM_SECTION = tr("Custom address")
NOT_REQUIRED = tr("Not required")
SAVED = tr("All changes saved")
UNSAVED = tr("Unsaved changes")
BUDGET_INVALID = tr("A budget must be a whole number of tokens, such as 200000 or 200k; empty means no limit.")
KEY_REMOVED = tr("The stored key for this endpoint was removed.")
KEY_HINT = tr("Kept in the QGIS authentication database.")
KEYLESS_HINT = tr("A local server needs no key.")
MODEL_HINT = tr("As the provider names it.")
# The pages the window builds on their first visit (`settings_layout.build_body` explains why).
DEFERRED_PAGES = {
    settings_layout.SKILLS: SkillsSettings,
    settings_layout.GEOCODING: GeocoderSettings,
    settings_layout.CONNECTORS: ConnectorsSettings,
    settings_layout.PERSONALISATION: PersonalisationSettings,
}


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
        self._probe_report = ("", "")
        # An example request picked on a connector page, for the chat box once the dialog closes.
        self.chosen_prompt = ""
        # What happened here that the plugin acts on once the dialog closes.
        self.history_erased = False
        self.was_reset = False
        palette = self.palette()
        self._palette = palette
        self._built_pages: dict[int, Any] = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        body, right = settings_layout.build_body(self, palette)
        column.addLayout(body, 1)
        right.addWidget(fields.separator(palette))
        footer = QHBoxLayout()
        footer.setContentsMargins(*FOOTER_MARGINS)
        footer.setSpacing(FOOTER_SPACING)
        self._saved_dot = controls.PaintedDot(FOOTER_DOT)
        self._saved_dot.set_colour(style.success(palette).name())
        footer.addWidget(self._saved_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._note = controls.small(SAVED, palette)
        self._note.setWordWrap(False)
        style.ink(self._note, style.muted(palette))
        footer.addWidget(self._note)
        self._status = fields.status(palette)
        footer.addWidget(self._status, 1)
        footer.addStretch(0)
        footer.addLayout(self._build_buttons(palette))
        right.addLayout(footer)
        self._sync_preset()
        self._load_endpoint_state(remember_current=False)
        self._show_untested()
        self._show_endpoint()
        self._watch_changes()

    def show_page(self, index: int) -> None:
        settings_layout.show_page(self, index)

    @property
    def skills(self) -> SkillsSettings:
        return self._page(settings_layout.SKILLS)

    @property
    def geocoder(self) -> GeocoderSettings:
        return self._page(settings_layout.GEOCODING)

    @property
    def connectors(self) -> ConnectorsSettings:
        return self._page(settings_layout.CONNECTORS)

    @property
    def personalisation(self) -> PersonalisationSettings:
        return self._page(settings_layout.PERSONALISATION)

    def build_page(self, index: int) -> QWidget:
        """Build a page left for its first visit; from then on its edits mark it as any other page's do."""
        page = DEFERRED_PAGES[index](self._palette)
        page.changed.connect(lambda *_args, at=index: self._mark_dirty(at))
        if index == settings_layout.CONNECTORS:
            page.prompt_chosen.connect(self._use_example)
            page.page_switched.connect(lambda: self.pages.currentWidget().verticalScrollBar().setValue(0))
        self._built_pages[index] = page
        return page.widget

    def _page(self, index: int) -> Any:
        """A deferred page's object, built now if nobody has visited it yet."""
        settings_layout.ensure_page(self, index)
        return self._built_pages[index]

    def _built(self, index: int) -> bool:
        return index in self._built_pages

    def _build_connection(self, palette: Any) -> QWidget:
        holder, column = fields.page(CONNECTION_TITLE, CONNECTION_LEAD, palette)
        self.test_btn = QPushButton(tr("Test connection"))
        self.test_btn.setStyleSheet(fields.plain_button(palette))
        self.test_btn.clicked.connect(self._test_connection)
        self.status_card = StatusCard(palette, self.test_btn)

        fields.section(column, tr("Provider"), palette)
        # The combo box stays the single source of truth for the preset; the tiles only draw it.
        self.preset_combo = QComboBox(holder)
        self.preset_combo.addItems(TITLES)
        self.preset_combo.hide()
        self.provider_tiles = ProviderTiles(PRESETS, palette)
        self.provider_tiles.chosen.connect(self.preset_combo.setCurrentText)
        self.preset_combo.currentTextChanged.connect(self.provider_tiles.select)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        column.addSpacing(fields.WIDE_GAP)
        column.addWidget(self.provider_tiles)

        # The section is named after the chosen provider, as the handoff draws it.
        column.addSpacing(fields.SECTION_GAP)
        self._endpoint_title = fields.heading("", palette)
        column.addWidget(self._endpoint_title)
        self.url_edit = QLineEdit(get_api_url())
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.url_edit.textChanged.connect(self._sync_preset)
        self.url_edit.textChanged.connect(self._show_endpoint)
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
                    fields.row(tr("Server address"), self.url_edit, tr("Without /chat/completions."), palette),
                    self._model_field,
                    self._key_field,
                ],
            )
        )
        column.addSpacing(fields.WIDE_GAP)
        column.addWidget(self.status_card)
        column.addStretch(1)
        return holder

    def _build_buttons(self, palette: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        close_btn = QPushButton(tr("Cancel"))
        close_btn.setStyleSheet(fields.plain_button(palette))
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
        """Mark a page as edited the moment one of its controls changes; Save waits for that.

        A deferred page is watched from its first visit, in `build_page`: unvisited, it holds no edits.
        """
        pages = {
            settings_layout.CONNECTION: [
                self.preset_combo.currentTextChanged,
                self.url_edit.textEdited,
                self.model_edit.textEdited,
                self.key_edit.textEdited,
            ],
            settings_layout.PRIVACY: [
                self.verify_ssl_cb.toggled,
                self.journal_cb.toggled,
                self.usage_cb.toggled,
                self.keep_choice.currentIndexChanged,
            ],
            settings_layout.ADVANCED: [
                self.verify_apply_cb.toggled,
                self.budget_edit.textChanged,
                self.steps_stepper.valueChanged,
                self.timeout_stepper.valueChanged,
                self.reasoning_cb.toggled,
                self.thinking_edit.textEdited,
                self.context_edit.textEdited,
                self.dialect_combo.currentIndexChanged,
                self.auth_type_combo.currentTextChanged,
                self.headers_edit.textChanged,
            ],
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
            self._saved_dot.set_colour(style.warning(self.palette()).name())

    def _show_endpoint(self, *_args: Any) -> None:
        """The Privacy page's line about where data goes follows the address being edited."""
        self.privacy_status.show_endpoint(self._edited_url())

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
            settings_advanced.select_data(self.dialect_combo, preset.dialect)
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
        self._endpoint_title.setText(CUSTOM_SECTION if preset.is_custom else preset.title)
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key or preset.is_custom)

    def _paint_key_hint(self, needs_key: bool) -> None:
        """A local server takes no key: the field greys out and says so, as the handoff draws it."""
        fields.set_row_hint(self._key_field, KEY_HINT if needs_key else KEYLESS_HINT)
        self.key_edit.setPlaceholderText(tr("Provider key") if needs_key else NOT_REQUIRED)
        self.key_edit.setEnabled(needs_key or bool(self.key_edit.text()))
        self.remove_key_btn.setVisible(needs_key)

    def _endpoint_finished(self, *_args: Any) -> None:
        if not self._loading_endpoint:
            self._load_endpoint_state()

    def _load_endpoint_state(self, remember_current: bool = True) -> None:
        if remember_current:
            self._remember_key_draft()
        url = self._edited_url()
        dialect = self._dialect()
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
        dialect = self._dialect()
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
        # A page never built holds what is stored already: only the built ones are saved.
        geocoder: tuple[str, str] | None = None
        if self._built(settings_layout.GEOCODING):
            try:
                geocoder = self.geocoder.values()
            except ValueError as error:
                self._show(str(error), style.danger(self.palette()))
                return
        dialect = self._dialect()
        model = self.model_edit.text().strip()
        if not model:
            self._show(MODEL_REQUIRED, style.danger(self.palette()))
            return
        problem = settings_advanced.problem(self)
        if problem:
            self._show(problem, style.danger(self.palette()))
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
        save_usage_choice(self.usage_cb.isChecked())
        set_token_budget(token_budget)
        set_thinking_budget(thinking_budget)
        set_context_window(context_window)
        set_reasoning_enabled(self.reasoning_cb.isChecked(), url, model, dialect)
        if geocoder is not None:
            set_geocoder_provider(geocoder[0])
        if self._built(settings_layout.CONNECTORS):
            save_enabled(self.connectors.enabled_ids())
        if self._built(settings_layout.SKILLS):
            set_disabled_skills(self.skills.disabled())
        settings_advanced.save(self)
        if self._built(settings_layout.PERSONALISATION):
            try:
                self.personalisation.save()
            except ValueError as error:
                self._show(str(error), style.danger(self.palette()))
                return
        if geocoder is not None and geocoder[0] == GEOCODER_NOMINATIM:
            set_custom_nominatim_url(geocoder[1])
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
        dialect = self._dialect()
        return {
            "url_override": url,
            "model_override": self.model_edit.text().strip() or None,
            "key_override": self.key_edit.text().strip() or get_api_key(url, dialect) or "",
            "auth_type_override": self.auth_type_combo.currentText() or None,
            "dialect_override": dialect or None,
            "verify_override": self.verify_ssl_cb.isChecked(),
            "extra_headers_override": self.headers_edit.toPlainText(),
        }

    def _dialect(self) -> str:
        return str(self.dialect_combo.currentData() or AUTO)
