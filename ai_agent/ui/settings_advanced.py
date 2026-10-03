from typing import Any

from qgis.PyQt.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from ai_agent.core.llm.dialects import DIALECTS
from ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    AUTH_TYPE_OAUTH,
    get_auth_type,
    get_dialect,
    get_reasoning_enabled,
    get_thinking_budget,
    get_token_budget,
    get_verify_after_apply,
    get_verify_ssl,
    get_write_run_journal,
)
from ai_agent.i18n import tr
from ai_agent.ui import controls
from ai_agent.ui import settings_fields as fields

DIALECT_HINT = tr("auto picks it from the address.")
AUTH_HINT = tr("Bearer suits almost everyone.")
VERIFY_LABEL = tr("Check the result after Apply")
VERIFY_HINT = tr("The agent re-reads the project to confirm the changes.")
BUDGET_LABEL = tr("Token budget per run")
BUDGET_HINT = tr("A run stops after this many tokens.")
REASONING_LABEL = tr("Reasoning")
REASONING_NOTE = tr("OpenAI-compatible APIs. Slower, more tokens.")
REASONING_HINT = tr(
    "Asks the model to think before it answers, in the parameter its provider expects. "
    "A server that rejects it is remembered and not asked again."
)
THINKING_LABEL = tr("Extended thinking budget")
THINKING_HINT = tr(
    "Anthropic only: 0 disables extended thinking. For Sonnet 5, any positive value enables adaptive thinking; "
    "older models require at least 1024 tokens and use the value as their reasoning budget."
)
SSL_LABEL = tr("Verify the SSL certificate")
SSL_HINT = tr("Turn off only for a trusted self-signed server.")
JOURNAL_LABEL = tr("Write a run journal after applying")
JOURNAL_NOTE = tr("A Markdown log in the QGIS profile.")
THINKING_NOTE = tr("Anthropic only. 0 turns it off.")
PRIVACY_CALLOUT = tr("Everything the agent reads goes to the model.")
PRIVACY_DETAIL = tr("Use a local server to keep project data on this computer.")
NO_LIMIT = tr("No limit")
BUDGET_PRESETS = [("100k", "100000"), ("300k", "300000"), ("1M", "1000000")]
BUDGET_FIELD_WIDTH = 96
THINKING_FIELD_WIDTH = 140
JOURNAL_HINT = tr(
    "Each applied run leaves an unencrypted Markdown file in the QGIS profile with the request, "
    "the tool names and the outcome. Off by default; the files stay until you delete them."
)


def build_privacy(owner: Any, palette: Any) -> QWidget:
    holder, column = fields.page()
    fields.section(column, PRIVACY_CALLOUT.rstrip("."), palette, PRIVACY_DETAIL)
    owner.verify_ssl_cb = fields.switch(palette)
    owner.verify_ssl_cb.setChecked(get_verify_ssl())
    owner.journal_cb = fields.switch(palette)
    owner.journal_cb.setToolTip(JOURNAL_HINT)
    owner.journal_cb.setChecked(get_write_run_journal())
    fields.section(column, tr("Connection security"), palette)
    column.addWidget(fields.card_rows(palette, [fields.switch_row(SSL_LABEL, owner.verify_ssl_cb, SSL_HINT, palette)]))
    fields.section(column, tr("Records"), palette)
    column.addWidget(
        fields.card_rows(
            palette, [fields.switch_row(JOURNAL_LABEL, owner.journal_cb, JOURNAL_NOTE, palette, JOURNAL_HINT)]
        )
    )
    column.addStretch(1)
    return holder


def build_advanced(owner: Any, palette: Any) -> QWidget:
    holder, column = fields.page()
    owner.verify_apply_cb = fields.switch(palette)
    owner.verify_apply_cb.setToolTip(VERIFY_HINT)
    owner.verify_apply_cb.setChecked(get_verify_after_apply())
    owner.budget_edit = QLineEdit(str(get_token_budget()))
    owner.reasoning_cb = fields.switch(palette)
    owner.reasoning_cb.setToolTip(REASONING_HINT)
    owner.reasoning_cb.setChecked(get_reasoning_enabled())
    owner.thinking_edit = QLineEdit(str(get_thinking_budget()))
    owner.thinking_edit.setStyleSheet(fields.input_style(palette))
    owner.thinking_edit.setFixedWidth(THINKING_FIELD_WIDTH)
    fields.section(column, tr("How the agent works"), palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.switch_row(VERIFY_LABEL, owner.verify_apply_cb, VERIFY_HINT, palette),
                fields.custom_row(BUDGET_LABEL, _budget_control(owner.budget_edit, palette), BUDGET_HINT, palette),
                fields.switch_row(REASONING_LABEL, owner.reasoning_cb, REASONING_NOTE, palette, REASONING_HINT),
                fields.custom_row(THINKING_LABEL, owner.thinking_edit, THINKING_NOTE, palette, THINKING_HINT),
            ],
        )
    )
    owner.dialect_combo = controls.Segmented(palette)
    owner.dialect_combo.addItems(list(DIALECTS))
    fields.select(owner.dialect_combo, get_dialect())
    owner.dialect_combo.currentTextChanged.connect(owner._endpoint_finished)
    owner.auth_type_combo = controls.Segmented(palette)
    owner.auth_type_combo.addItems([AUTH_TYPE_BEARER, AUTH_TYPE_OAUTH])
    fields.select(owner.auth_type_combo, get_auth_type())
    fields.section(column, tr("Talking to the provider"), palette)
    column.addWidget(
        fields.card_rows(
            palette,
            [
                fields.custom_row(tr("API format"), owner.dialect_combo, DIALECT_HINT, palette),
                fields.custom_row(tr("Authorisation type"), owner.auth_type_combo, AUTH_HINT, palette),
            ],
        )
    )
    column.addStretch(1)
    return holder


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
