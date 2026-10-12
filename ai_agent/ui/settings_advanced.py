"""The Privacy and Advanced pages, and what their buttons do: erase the history, reset the preferences."""

from typing import Any

from qgis.PyQt.QtCore import QLocale, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QFontDatabase
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.config import limits
from ai_agent.core import history
from ai_agent.core.llm import extra_headers
from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import ANTHROPIC, AUTO, OPENAI
from ai_agent.core.privacy import endpoint_label
from ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    AUTH_TYPE_OAUTH,
    get_auth_type,
    get_context_window,
    get_dialect,
    get_extra_headers,
    get_history_days,
    get_reasoning_enabled,
    get_thinking_budget,
    get_token_budget,
    get_verify_after_apply,
    get_verify_ssl,
    get_write_run_journal,
    reset_preferences,
    set_extra_headers,
    set_history_days,
)
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

PRIVACY_TITLE = tr("Privacy")
PRIVACY_LEAD = tr("Everything the agent reads goes to the model you chose. Here: where it goes and what stays on disk.")
LOCAL_TITLE = tr("Data stays on this computer")
LOCAL_DETAIL = tr("The model runs at {0}, on this device.")
REMOTE_TITLE = tr("Data goes to the provider")
REMOTE_DETAIL = tr("What the agent reads is sent to {0}. For data that must stay here, use a local server.")
TO_CONNECTION = tr("Connection")
CONNECTION_SECTION = tr("Network")
SSL_LABEL = tr("Verify the SSL certificate")
SSL_HINT = tr("Turn off only for a trusted self-signed server.")
HISTORY_SECTION = tr("History and journals")
KEEP_LABEL = tr("Keep conversations")
KEEP_TITLES = {7: tr("7 days"), 30: tr("30 days"), 0: tr("Always")}
JOURNAL_LABEL = tr("Run journal")
JOURNAL_NOTE = tr("A Markdown file with the steps and calls after every Apply.")
JOURNAL_HINT = tr(
    "Each applied run leaves an unencrypted Markdown file in the QGIS profile with the request, "
    "the tool names and the outcome. Off by default; the files stay until you delete them."
)
FOLDER_LABEL = tr("Folder")
OPEN = tr("Open")
ERASE_LABEL = tr("Delete history and journals")
ERASE_NOTE = tr("{0}, {1}. This cannot be undone.")
ERASE_EMPTY = tr("Nothing is kept yet.")
ERASE_BUTTON = tr("Delete…")
ERASE_QUESTION = tr("Delete every saved conversation of every project, and every run journal? This cannot be undone.")
ERASED = tr("History and journals deleted.")
ADVANCED_TITLE = tr("Advanced")
ADVANCED_LEAD = tr("Limits and fine tuning. The defaults suit most people.")
AGENT_SECTION = tr("How the agent works")
VERIFY_LABEL = tr("Check the result after Apply")
VERIFY_HINT = tr("The agent re-reads the project to confirm the changes.")
BUDGET_LABEL = tr("Token budget per run")
BUDGET_HINT = tr("A run stops after this many tokens.")
STEPS_LABEL = tr("Steps per run, at most")
STEPS_HINT = tr("Every tool call is one step.")
TIMEOUT_LABEL = tr("Tool timeout")
TIMEOUT_HINT = tr("Raise it for long Processing algorithms.")
SECONDS = tr(" s")
MODEL_SECTION = tr("Model")
CONTEXT_LABEL = tr("Context window")
CONTEXT_NOTE = tr("Empty finds it on its own.")
CONTEXT_AUTO = tr("Auto")
CONTEXT_HINT = tr(
    "How many tokens the model reads at once. Left empty, the plugin asks the server at the connection "
    "test and otherwise guesses from the model's name. The conversation is compacted at 90 % of it."
)
REASONING_LABEL = tr("Reasoning")
REASONING_NOTE = tr("OpenAI-compatible APIs. Slower, more tokens.")
REASONING_HINT = tr(
    "Asks the model to think before it answers, in the parameter its provider expects. "
    "A server that rejects it is skipped from then on; a connection test, "
    "or saving the switch off and then on, asks it again."
)
THINKING_LABEL = tr("Extended thinking budget")
THINKING_NOTE = tr("Anthropic only. 0 turns it off.")
THINKING_HINT = tr(
    "Anthropic only: 0 disables extended thinking. For Sonnet 5, any positive value enables adaptive thinking; "
    "older models require at least 1024 tokens and use the value as their reasoning budget."
)
PROVIDER_SECTION = tr("Talking to the provider")
DIALECT_LABEL = tr("API format")
DIALECT_HINT = tr("Auto picks it from the address.")
DIALECT_TITLES = {AUTO: tr("Auto"), OPENAI: "OpenAI", ANTHROPIC: "Anthropic"}
AUTH_LABEL = tr("Authorisation")
AUTH_HINT = tr("Bearer suits almost everyone.")
HEADERS_LABEL = tr("Extra headers")
HEADERS_NOTE = tr("One per line, Name: value. Keys go in the API key field.")
HEADERS_PLACEHOLDER = "x-folder-id: b1g8f3k2…"
RESET_LABEL = tr("Reset agent settings")
RESET_NOTE = tr("The connection, keys, your own texts and skills stay.")
RESET_BUTTON = tr("Reset…")
RESET_QUESTION = tr(
    "Return limits, modes, connectors, skills, geocoding and personalisation choices to their defaults? "
    "The connection, keys, your own texts and skills stay."
)
NO_LIMIT = tr("No limit")
BUDGET_PRESETS = [("100k", "100000"), ("300k", "300000"), ("1M", "1000000")]
BUDGET_FIELD_WIDTH = 96
THINKING_FIELD_WIDTH = 140
HEADERS_HEIGHT = 56
FOLDER_WIDTH = 240
STATUS_RADIUS = 8
STATUS_MARGINS = (14, 12, 14, 12)
SHIELD_TILE = 30
SHIELD = 16
BYTES_IN_MB = 1024 * 1024
BYTES_IN_KB = 1024


def build_privacy(owner: Any, palette: Any) -> QWidget:
    holder, column = fields.page(PRIVACY_TITLE, PRIVACY_LEAD, palette)
    column.addSpacing(fields.SECTION_GAP)
    owner.privacy_status = PrivacyStatus(palette)
    owner.privacy_status.to_connection.clicked.connect(lambda: owner.show_page(0))
    column.addWidget(owner.privacy_status)
    owner.verify_ssl_cb = fields.switch(palette)
    owner.verify_ssl_cb.setChecked(get_verify_ssl())
    fields.section(column, CONNECTION_SECTION, palette)
    column.addWidget(fields.card_rows(palette, [fields.switch_row(SSL_LABEL, owner.verify_ssl_cb, SSL_HINT, palette)]))
    owner.keep_choice = controls.Segmented(palette)
    for days, title in KEEP_TITLES.items():
        owner.keep_choice.addItem(title, days)
    owner.keep_choice.setCurrentIndex(max(0, owner.keep_choice.findData(get_history_days())))
    owner.journal_cb = fields.switch(palette)
    owner.journal_cb.setToolTip(JOURNAL_HINT)
    owner.journal_cb.setChecked(get_write_run_journal())
    owner.erase_btn = QPushButton(ERASE_BUTTON)
    owner.erase_btn.setStyleSheet(fields.danger_button(palette))
    owner.erase_btn.clicked.connect(lambda: erase_history(owner))
    owner.erase_row = fields.custom_row(ERASE_LABEL, owner.erase_btn, "", palette)
    fields.section(column, HISTORY_SECTION, palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.custom_row(KEEP_LABEL, owner.keep_choice, "", palette),
                fields.switch_row(JOURNAL_LABEL, owner.journal_cb, JOURNAL_NOTE, palette, JOURNAL_HINT),
                fields.custom_row(FOLDER_LABEL, _folder(history.journals_folder(), palette), "", palette),
                owner.erase_row,
            ],
        )
    )
    show_history_size(owner)
    column.addStretch(1)
    return holder


def build_advanced(owner: Any, palette: Any) -> QWidget:
    holder, column = fields.page(ADVANCED_TITLE, ADVANCED_LEAD, palette)
    owner.verify_apply_cb = fields.switch(palette)
    owner.verify_apply_cb.setToolTip(VERIFY_HINT)
    owner.verify_apply_cb.setChecked(get_verify_after_apply())
    owner.budget_edit = QLineEdit(str(get_token_budget()))
    owner.steps_stepper = fields.Stepper(
        palette, limits.max_steps(), limits.MIN_STEPS, limits.MAX_STEPS, limits.STEPS_INCREMENT
    )
    owner.timeout_stepper = fields.Stepper(
        palette,
        limits.tool_seconds(),
        limits.MIN_TOOL_SECONDS,
        limits.MAX_TOOL_SECONDS,
        limits.TOOL_SECONDS_INCREMENT,
        SECONDS,
    )
    fields.section(column, AGENT_SECTION, palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.switch_row(VERIFY_LABEL, owner.verify_apply_cb, VERIFY_HINT, palette),
                fields.custom_row(BUDGET_LABEL, _budget_control(owner.budget_edit, palette), BUDGET_HINT, palette),
                fields.custom_row(STEPS_LABEL, owner.steps_stepper, STEPS_HINT, palette),
                fields.custom_row(TIMEOUT_LABEL, owner.timeout_stepper, TIMEOUT_HINT, palette),
            ],
        )
    )
    owner.context_edit = QLineEdit(str(get_context_window() or ""))
    owner.context_edit.setPlaceholderText(CONTEXT_AUTO)
    owner.context_edit.setStyleSheet(fields.input_style(palette))
    owner.context_edit.setFixedWidth(THINKING_FIELD_WIDTH)
    owner.reasoning_cb = fields.switch(palette)
    owner.reasoning_cb.setToolTip(REASONING_HINT)
    owner.reasoning_cb.setChecked(get_reasoning_enabled())
    owner.thinking_edit = QLineEdit(str(get_thinking_budget()))
    owner.thinking_edit.setStyleSheet(fields.input_style(palette))
    owner.thinking_edit.setFixedWidth(THINKING_FIELD_WIDTH)
    fields.section(column, MODEL_SECTION, palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.custom_row(CONTEXT_LABEL, owner.context_edit, CONTEXT_NOTE, palette, CONTEXT_HINT),
                fields.switch_row(REASONING_LABEL, owner.reasoning_cb, REASONING_NOTE, palette, REASONING_HINT),
                fields.custom_row(THINKING_LABEL, owner.thinking_edit, THINKING_NOTE, palette, THINKING_HINT),
            ],
        )
    )
    owner.dialect_combo = controls.Segmented(palette)
    for dialect, title in DIALECT_TITLES.items():
        owner.dialect_combo.addItem(title, dialect)
    select_data(owner.dialect_combo, get_dialect())
    owner.dialect_combo.currentIndexChanged.connect(owner._endpoint_finished)
    owner.auth_type_combo = controls.Segmented(palette)
    owner.auth_type_combo.addItems([AUTH_TYPE_BEARER, AUTH_TYPE_OAUTH])
    fields.select(owner.auth_type_combo, get_auth_type())
    owner.headers_edit = QPlainTextEdit(get_extra_headers())
    owner.headers_edit.setPlaceholderText(HEADERS_PLACEHOLDER)
    owner.headers_edit.setFixedHeight(HEADERS_HEIGHT)
    owner.headers_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    owner.headers_edit.setStyleSheet(_area_style(palette))
    fields.section(column, PROVIDER_SECTION, palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.custom_row(DIALECT_LABEL, owner.dialect_combo, DIALECT_HINT, palette),
                fields.custom_row(AUTH_LABEL, owner.auth_type_combo, AUTH_HINT, palette),
                fields.wide_row(HEADERS_LABEL, owner.headers_edit, HEADERS_NOTE, palette),
            ],
        )
    )
    reset = QPushButton(RESET_BUTTON)
    reset.setStyleSheet(fields.danger_button(palette))
    reset.clicked.connect(lambda: reset_settings(owner))
    fields.section(column, "", palette)
    column.addWidget(fields.card_rows(palette, [fields.custom_row(RESET_LABEL, reset, RESET_NOTE, palette)]))
    column.addStretch(1)
    return holder


def problem(owner: Any) -> str:
    """Why these pages cannot be saved as they are, or "" when they can."""
    try:
        extra_headers.parse(owner.headers_edit.toPlainText())
    except ValueError as error:
        return str(error)
    return ""


def save(owner: Any) -> None:
    """Store what these pages hold beyond the connection; `problem` has checked it first."""
    set_extra_headers(owner.headers_edit.toPlainText())
    set_history_days(int(owner.keep_choice.currentData() or 0))
    limits.set_max_steps(owner.steps_stepper.value())
    limits.set_tool_seconds(owner.timeout_stepper.value())


def select_data(choice: Any, value: Any) -> None:
    index = choice.findData(value)
    if index >= 0:
        choice.setCurrentIndex(index)


def show_history_size(owner: Any) -> None:
    conversations, size = history.usage()
    note = ERASE_NOTE.format(tr_n("%n conversation(s)", conversations), _size(size)) if size else ERASE_EMPTY
    fields.set_row_hint(owner.erase_row, note)
    owner.erase_btn.setEnabled(bool(size))


def erase_history(owner: Any) -> None:
    """Ask, then delete every kept conversation and journal; the dialog's owner drops the open conversation."""
    if QMessageBox.question(owner, ERASE_LABEL, ERASE_QUESTION) != QMessageBox.StandardButton.Yes:
        return
    history.erase()
    owner.history_erased = True
    show_history_size(owner)
    owner._show(ERASED, style.success(owner.palette()))


def reset_settings(owner: Any) -> None:
    """Ask, then return the preferences to their defaults and close: reopened, the window shows them."""
    if QMessageBox.question(owner, RESET_LABEL, RESET_QUESTION) != QMessageBox.StandardButton.Yes:
        return
    reset_preferences()
    owner.was_reset = True
    owner.accept()


class PrivacyStatus(controls.RoundedFrame):
    """Where the data goes, read from the address on the Connection page: this computer, or a provider."""

    def __init__(self, palette: Any):
        super().__init__(STATUS_RADIUS)
        self._palette = palette
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        line = QHBoxLayout(self)
        line.setContentsMargins(*STATUS_MARGINS)
        line.setSpacing(12)
        self._shield = QLabel()
        self._shield.setFixedSize(SHIELD_TILE, SHIELD_TILE)
        self._shield.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line.addWidget(self._shield, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel()
        style.scale_font(self.title, 1.0, bold=True)
        style.ink(self.title, style.text(palette))
        text.addWidget(self.title)
        self.detail = controls.small("", palette)
        text.addWidget(self.detail)
        line.addLayout(text, 1)
        self.to_connection = QPushButton(TO_CONNECTION)
        self.to_connection.setStyleSheet(fields.plain_button(palette))
        line.addWidget(self.to_connection, 0, Qt.AlignmentFlag.AlignVCenter)

    def show_endpoint(self, url: str) -> None:
        local = is_local(url)
        colour = style.success(self._palette) if local else style.warning(self._palette)
        self._shield.setStyleSheet(
            f"QLabel {{ background: {style.css_color(style.soft(self._palette, colour))};"
            f"border-radius: {SHIELD_TILE // 2}px; }}"
        )
        glyph = icons.drawn("privacy", colour, SHIELD)
        if glyph is not None:
            self._shield.setPixmap(glyph.pixmap(SHIELD, SHIELD))
        self.title.setText(LOCAL_TITLE if local else REMOTE_TITLE)
        self.detail.setText((LOCAL_DETAIL if local else REMOTE_DETAIL).format(endpoint_label(url)))


def _folder(path: str, palette: Any) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    shown = controls.ElidedLabel(path, mode=Qt.TextElideMode.ElideMiddle)
    shown.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    shown.setToolTip(path)
    # A path as wide as a field, its middle elided: an elided label asks for no width of its own.
    shown.setFixedWidth(FOLDER_WIDTH)
    style.ink(shown, style.muted(palette))
    line.addWidget(shown, 1)
    button = QPushButton(OPEN)
    button.setStyleSheet(fields.plain_button(palette))
    button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
    line.addWidget(button)
    return holder


def _size(size: int) -> str:
    locale = QLocale()
    if size >= BYTES_IN_MB:
        return tr("{0} MB").format(locale.toString(size / BYTES_IN_MB, "f", 1))
    return tr("{0} KB").format(locale.toString(max(1, round(size / BYTES_IN_KB))))


def _budget_control(edit: QLineEdit, palette: Any) -> QWidget:
    """Preset chips next to the field: one click for the usual values, typing for the rest."""
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    line.addWidget(controls.Chips(palette, edit, [*BUDGET_PRESETS, (NO_LIMIT, "0")], fields.parsed_budget))
    edit.setStyleSheet(fields.input_style(palette))
    edit.setFixedWidth(BUDGET_FIELD_WIDTH)
    line.addWidget(edit)
    return holder


def _area_style(palette: Any) -> str:
    border = style.css_color(style.border_strong(palette))
    return (
        f"QPlainTextEdit {{ background: {style.css_color(style.field(palette))};"
        f"color: {style.css_color(style.text(palette))}; border: {style.HAIRLINE}px solid {border};"
        f"border-radius: {fields.INPUT_RADIUS}px; padding: 4px 6px; }}"
        f"QPlainTextEdit:focus {{ border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
    )
