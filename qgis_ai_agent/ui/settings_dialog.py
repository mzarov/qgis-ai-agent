from typing import Any

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.core.llm.dialects import DIALECTS
from qgis_ai_agent.core.llm.probe import probe
from qgis_ai_agent.core.llm.providers import TITLES, by_title, matching
from qgis_ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    AUTH_TYPE_OAUTH,
    DEFAULT_TOKEN_BUDGET,
    get_api_key,
    get_api_url,
    get_auth_type,
    get_dialect,
    get_model,
    get_token_budget,
    get_verify_after_apply,
    get_verify_ssl,
    set_api_key,
    set_api_url,
    set_auth_type,
    set_dialect,
    set_model,
    set_token_budget,
    set_verify_after_apply,
    set_verify_ssl,
)
from qgis_ai_agent.i18n import tr
from qgis_ai_agent.ui import settings_fields as fields
from qgis_ai_agent.ui import style

TITLE = tr("Settings — QGIS AI Agent")
MIN_WIDTH = 520
MARGINS = (16, 16, 16, 14)
SPACING = 12
SAVED = tr("Settings saved.")
TESTING = tr("Testing the connection…")
KEY_HINT = tr("Stored in the system keyring, not in the settings file.")
KEYLESS_HINT = tr("A local server needs no key — leave this empty.")
DIALECT_HINT = tr("auto picks the format from the address: api.anthropic.com is Anthropic, everything else is OpenAI.")
AUTH_HINT = tr("Bearer suits almost everyone; OAuth is for corporate gateways.")
VERIFY_LABEL = tr("Check the result after applying changes")
VERIFY_HINT = tr("After you press Apply, the agent re-reads the project and confirms the changes really landed.")
BUDGET_LABEL = tr("Token budget per run")
BUDGET_HINT = tr("The run stops politely once it has spent this many tokens. 0 removes the limit.")


class SettingsDialog(QDialog):
    def __init__(self, parent: Any = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(MIN_WIDTH)
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(*MARGINS)
        column.setSpacing(SPACING)
        column.addWidget(self._build_connection(palette))
        column.addWidget(self._build_advanced(palette))
        self._status = fields.status(palette)
        column.addWidget(self._status)
        column.addStretch(1)
        column.addLayout(self._build_buttons(palette))
        self._sync_preset()

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
        column.addWidget(
            fields.field(tr("Base URL"), self.url_edit, tr("Without /chat/completions at the end."), palette)
        )

        self.model_edit = QLineEdit(get_model())
        column.addWidget(fields.field(tr("Model"), self.model_edit, "", palette))

        self.key_edit = QLineEdit(get_api_key())
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(tr("Provider key"))
        self._key_field = fields.field(tr("API key"), self.key_edit, KEY_HINT, palette)
        column.addWidget(self._key_field)
        return frame

    def _build_advanced(self, palette: Any) -> QWidget:
        frame, column = fields.card(palette)
        column.addWidget(fields.section(tr("Advanced"), palette))

        self.dialect_combo = QComboBox()
        self.dialect_combo.addItems(list(DIALECTS))
        _select(self.dialect_combo, get_dialect())
        column.addWidget(fields.field(tr("API format"), self.dialect_combo, DIALECT_HINT, palette))

        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems([AUTH_TYPE_BEARER, AUTH_TYPE_OAUTH])
        _select(self.auth_type_combo, get_auth_type())
        column.addWidget(fields.field(tr("Authorisation type"), self.auth_type_combo, AUTH_HINT, palette))

        self.verify_ssl_cb = QCheckBox(tr("Verify the SSL certificate"))
        self.verify_ssl_cb.setChecked(get_verify_ssl())
        column.addWidget(self.verify_ssl_cb)

        self.verify_apply_cb = QCheckBox(VERIFY_LABEL)
        self.verify_apply_cb.setToolTip(VERIFY_HINT)
        self.verify_apply_cb.setChecked(get_verify_after_apply())
        column.addWidget(self.verify_apply_cb)

        self.budget_edit = QLineEdit(str(get_token_budget()))
        column.addWidget(fields.field(BUDGET_LABEL, self.budget_edit, BUDGET_HINT, palette))
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
        preset = by_title(title)
        if preset.is_custom:
            self._paint_key_hint(True)
            return
        self.url_edit.setText(preset.url)
        _select(self.dialect_combo, preset.dialect)
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key)

    def _sync_preset(self) -> None:
        preset = matching(self.url_edit.text())
        _select(self.preset_combo, preset.title)
        self.model_edit.setPlaceholderText(preset.model_hint)
        self._paint_key_hint(preset.needs_key or preset.is_custom)

    def _paint_key_hint(self, needs_key: bool) -> None:
        self._key_field.setToolTip(KEY_HINT if needs_key else KEYLESS_HINT)
        self.key_edit.setPlaceholderText(tr("Provider key") if needs_key else tr("Not required"))

    def _save(self) -> None:
        set_api_url(self.url_edit.text().strip() or None)
        set_model(self.model_edit.text().strip() or None)
        set_auth_type(self.auth_type_combo.currentText())
        set_dialect(self.dialect_combo.currentText())
        set_verify_ssl(self.verify_ssl_cb.isChecked())
        set_verify_after_apply(self.verify_apply_cb.isChecked())
        set_token_budget(_parsed_budget(self.budget_edit.text()))
        key = self.key_edit.text()
        if key:
            try:
                set_api_key(key)
            except RuntimeError as error:
                self._show(str(error), style.danger(self.palette()))
                return
        self._show(SAVED, style.success(self.palette()))

    def _test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self._show(TESTING, style.muted(self.palette()))
        try:
            ok, message = probe(self._overrides())
        finally:
            self.test_btn.setEnabled(True)
        palette = self.palette()
        self._show(message, style.success(palette) if ok else style.danger(palette))

    def _overrides(self) -> dict[str, Any]:
        return {
            "url_override": self.url_edit.text().strip() or None,
            "model_override": self.model_edit.text().strip() or None,
            "key_override": self.key_edit.text().strip() or get_api_key() or None,
            "auth_type_override": self.auth_type_combo.currentText() or None,
            "dialect_override": self.dialect_combo.currentText() or None,
            "verify_override": self.verify_ssl_cb.isChecked(),
        }

    def _show(self, message: str, colour: Any) -> None:
        fields.paint_status(self._status, message, colour)


def _parsed_budget(raw: str) -> int:
    try:
        return max(0, int(raw.strip()))
    except (TypeError, ValueError):
        return DEFAULT_TOKEN_BUDGET


def _select(combo: QComboBox, value: str) -> None:
    index = combo.findText(value or "")
    if index >= 0:
        combo.setCurrentIndex(index)
