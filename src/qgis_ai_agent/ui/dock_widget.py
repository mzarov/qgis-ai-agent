from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui.chat import ChatView

PROMPT_PLACEHOLDER = (
    "Например: что у меня в проекте? — или: построй буфер 500 метров вокруг городов"
)
PROMPT_HEIGHT = 60
CHAT_MIN_HEIGHT = 120
BUSY_TEXT = "Работаю…"


class AgentDockWidget(QDockWidget):
    open_settings_clicked = pyqtSignal()
    prompt_submitted = pyqtSignal(str)
    confirm_plan_clicked = pyqtSignal()
    cancel_plan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS AI Agent")
        self.main_widget = QWidget()
        layout = QVBoxLayout(self.main_widget)
        layout.addWidget(QLabel("Чат:"))
        self.chat_view = ChatView(self.main_widget)
        self.chat_view.setMinimumHeight(CHAT_MIN_HEIGHT)
        layout.addWidget(self.chat_view)
        layout.addWidget(QLabel("Ваш запрос:"))
        layout.addWidget(self._build_prompt())
        layout.addLayout(self._build_send_row())
        layout.addLayout(self._build_confirm_row())
        layout.addWidget(self._build_settings_button())
        self.set_confirm_visible(False)
        self.setWidget(self.main_widget)

    def _build_prompt(self) -> QPlainTextEdit:
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(PROMPT_PLACEHOLDER)
        self.prompt_edit.setMaximumHeight(PROMPT_HEIGHT)
        return self.prompt_edit

    def _build_send_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.send_btn = QPushButton("Отправить")
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.send_btn)
        self.busy_label = QLabel("")
        row.addWidget(self.busy_label)
        return row

    def _build_confirm_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.confirm_btn = QPushButton("Применить изменения")
        self.confirm_btn.clicked.connect(self.confirm_plan_clicked.emit)
        row.addWidget(self.confirm_btn)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_plan_clicked.emit)
        row.addWidget(self.cancel_btn)
        return row

    def _build_settings_button(self) -> QPushButton:
        button = QPushButton("Настройки")
        button.clicked.connect(self.open_settings_clicked.emit)
        return button

    def add_user_message(self, text: str) -> int:
        return self.chat_view.add_user_message(text)

    def add_system_message(self, text: str) -> int:
        return self.chat_view.add_system_message(text)

    def add_result_message(self, text: str) -> int:
        return self.chat_view.add_result_message(text)

    def add_tool_message(self, text: str) -> int:
        return self.chat_view.add_tool_message(text)

    def add_rejected_message(self, text: str) -> int:
        return self.chat_view.add_rejected_message(text)

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        self.chat_view.mark_tool_done(message_id, ok)

    def add_plan_message(self, plan_lines: list[str]) -> int:
        return self.chat_view.add_plan_message(plan_lines)

    def mark_plan_completed(self, message_id: int) -> None:
        self.chat_view.mark_plan_completed(message_id)

    def set_confirm_visible(self, visible: bool) -> None:
        self.confirm_btn.setVisible(visible)
        self.cancel_btn.setVisible(visible)

    def set_busy(self, busy: bool) -> None:
        self.send_btn.setEnabled(not busy)
        self.busy_label.setText(BUSY_TEXT if busy else "")

    def _on_send(self) -> None:
        self.prompt_submitted.emit(self.prompt_edit.toPlainText().strip())
