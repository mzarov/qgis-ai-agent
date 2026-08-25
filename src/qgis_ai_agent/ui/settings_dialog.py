from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from qgis_ai_agent.core.llm.dialects import DIALECTS
from qgis_ai_agent.core.settings import (
    AUTH_TYPE_BEARER,
    AUTH_TYPE_OAUTH,
    get_api_key,
    get_api_url,
    get_auth_type,
    get_model,
    get_dialect,
    get_verify_ssl,
    set_api_key,
    set_api_url,
    set_auth_type,
    set_dialect,
    set_model,
    set_verify_ssl,
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки — QGIS AI Agent")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.setText(get_api_url())
        form.addRow("Базовый URL API:", self.url_edit)

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("gpt-4o-mini")
        self.model_edit.setText(get_model())
        form.addRow("Модель:", self.model_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Оставьте пустым, чтобы не менять")
        self.key_edit.setText(get_api_key())
        form.addRow("API-ключ:", self.key_edit)

        self.dialect_combo = QComboBox()
        self.dialect_combo.addItems(list(DIALECTS))
        index = self.dialect_combo.findText(get_dialect())
        if index >= 0:
            self.dialect_combo.setCurrentIndex(index)
        self.dialect_combo.setToolTip(
            "auto определяет формат по адресу: api.anthropic.com — Anthropic, "
            "всё остальное — OpenAI-совместимый."
        )
        form.addRow("Формат API:", self.dialect_combo)

        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems([AUTH_TYPE_BEARER, AUTH_TYPE_OAUTH])
        idx = self.auth_type_combo.findText(get_auth_type())
        if idx >= 0:
            self.auth_type_combo.setCurrentIndex(idx)
        form.addRow("Тип авторизации:", self.auth_type_combo)

        self.verify_ssl_cb = QCheckBox("Проверять SSL-сертификат")
        self.verify_ssl_cb.setChecked(get_verify_ssl())
        form.addRow("", self.verify_ssl_cb)

        layout.addLayout(form)

        self.test_btn = QPushButton("Проверить подключение")
        self.test_btn.clicked.connect(self._test_connection)
        layout.addWidget(self.test_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        url = self.url_edit.text().strip()
        model = self.model_edit.text().strip()
        key = self.key_edit.text()
        set_api_url(url or None)
        set_model(model or None)
        set_auth_type(self.auth_type_combo.currentText())
        set_dialect(self.dialect_combo.currentText())
        set_verify_ssl(self.verify_ssl_cb.isChecked())
        if key:
            try:
                set_api_key(key)
            except RuntimeError as error:
                QMessageBox.warning(self, "Ключ не сохранён", str(error))
                return
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def _test_connection(self):
        from qgis_ai_agent.core.llm.client import chat

        self.test_btn.setEnabled(False)
        try:
            url = self.url_edit.text().strip()
            model = self.model_edit.text().strip()
            key = self.key_edit.text().strip() or get_api_key()
            auth_type = self.auth_type_combo.currentText()
            dialect = self.dialect_combo.currentText()
            verify = self.verify_ssl_cb.isChecked()
            reply = chat(
                [{"role": "user", "content": "Ответь одним словом: ок"}],
                url_override=url or None,
                model_override=model or None,
                key_override=key or None,
                auth_type_override=auth_type or None,
                dialect_override=dialect or None,
                verify_override=verify,
            )
            QMessageBox.information(
                self,
                "Проверка подключения",
                f"Ответ модели: {reply[:200]}" + ("..." if len(reply) > 200 else ""),
            )
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))
        finally:
            self.test_btn.setEnabled(True)
