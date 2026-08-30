from typing import Any

from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QLineEdit, QWidget

from ai_agent.core.llm.dialects import DIALECTS
from ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    AUTH_TYPE_OAUTH,
    get_auth_type,
    get_dialect,
    get_thinking_budget,
    get_token_budget,
    get_verify_after_apply,
    get_verify_ssl,
)
from ai_agent.i18n import tr
from ai_agent.ui import settings_fields as fields

DIALECT_HINT = tr("auto picks the format from the address: api.anthropic.com is Anthropic, everything else is OpenAI.")
AUTH_HINT = tr("Bearer suits almost everyone; OAuth is for corporate gateways.")
VERIFY_LABEL = tr("Check the result after applying changes")
VERIFY_HINT = tr("After you press Apply, the agent re-reads the project and confirms the changes really landed.")
BUDGET_LABEL = tr("Token budget per run")
BUDGET_HINT = tr("The run stops politely once it has spent this many tokens. 0 removes the limit.")
THINKING_LABEL = tr("Extended thinking budget")
THINKING_HINT = tr(
    "Anthropic only: 0 disables extended thinking. For Sonnet 5, any positive value enables adaptive thinking; "
    "older models require at least 1024 tokens and use the value as their reasoning budget."
)
SSL_LABEL = tr("Verify the SSL certificate")


def build_privacy(owner: Any, palette: Any) -> QWidget:
    holder, column = fields.page()
    owner.data_sharing_cb = QCheckBox(owner.sharing_label)
    owner.data_sharing_cb.setToolTip(owner.sharing_hint)
    column.addWidget(owner.data_sharing_cb)
    column.addWidget(fields.hint(owner.sharing_hint, palette))
    owner.sensitive_data_cb = QCheckBox(owner.sensitive_label)
    owner.sensitive_data_cb.setToolTip(owner.sensitive_hint)
    column.addWidget(owner.sensitive_data_cb)
    column.addWidget(fields.hint(owner.sensitive_hint, palette))
    owner.data_sharing_cb.toggled.connect(owner.sensitive_data_cb.setEnabled)
    owner.verify_ssl_cb = QCheckBox(SSL_LABEL)
    owner.verify_ssl_cb.setChecked(get_verify_ssl())
    column.addWidget(owner.verify_ssl_cb)
    column.addStretch(1)
    return holder


def build_advanced(owner: Any, palette: Any, geocoder: QWidget) -> QWidget:
    holder, column = fields.page()
    column.addWidget(geocoder)
    owner.dialect_combo = QComboBox()
    owner.dialect_combo.addItems(list(DIALECTS))
    fields.select(owner.dialect_combo, get_dialect())
    owner.dialect_combo.currentTextChanged.connect(owner._endpoint_finished)
    column.addWidget(fields.field(tr("API format"), owner.dialect_combo, DIALECT_HINT, palette))
    owner.auth_type_combo = QComboBox()
    owner.auth_type_combo.addItems([AUTH_TYPE_BEARER, AUTH_TYPE_OAUTH])
    fields.select(owner.auth_type_combo, get_auth_type())
    column.addWidget(fields.field(tr("Authorisation type"), owner.auth_type_combo, AUTH_HINT, palette))
    owner.verify_apply_cb = QCheckBox(VERIFY_LABEL)
    owner.verify_apply_cb.setToolTip(VERIFY_HINT)
    owner.verify_apply_cb.setChecked(get_verify_after_apply())
    column.addWidget(owner.verify_apply_cb)
    owner.budget_edit = QLineEdit(str(get_token_budget()))
    column.addWidget(fields.field(BUDGET_LABEL, owner.budget_edit, BUDGET_HINT, palette))
    owner.thinking_edit = QLineEdit(str(get_thinking_budget()))
    column.addWidget(fields.field(THINKING_LABEL, owner.thinking_edit, THINKING_HINT, palette))
    column.addStretch(1)
    return holder
