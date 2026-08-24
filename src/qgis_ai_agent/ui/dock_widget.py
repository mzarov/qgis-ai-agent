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


class LayoutAgentDockWidget(QDockWidget):
    open_settings_clicked = pyqtSignal()
    create_layout_from_prompt_clicked = pyqtSignal(str)
    confirm_plan_clicked = pyqtSignal()
    cancel_plan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS AI Agent")
        self.main_widget = QWidget()
        layout = QVBoxLayout(self.main_widget)

        layout.addWidget(QLabel("QGIS AI Agent"))
        layout.addWidget(QLabel("Чат:"))
        self.chat_view = ChatView(self.main_widget)
        self.chat_view.setMinimumHeight(120)
        layout.addWidget(self.chat_view)

        layout.addWidget(QLabel("Ваш запрос:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Например: создай макет A4 с картой и легендой — или: обработай слои (модель ответит, что пока не умеет)")
        self.prompt_edit.setMaximumHeight(60)
        layout.addWidget(self.prompt_edit)

        row = QHBoxLayout()
        self.send_btn = QPushButton("Отправить")
        self.send_btn.clicked.connect(self._on_create_from_prompt)
        row.addWidget(self.send_btn)
        self.busy_label = QLabel("")
        row.addWidget(self.busy_label)
        layout.addLayout(row)

        confirm_row = QHBoxLayout()
        self.confirm_btn = QPushButton("Применить изменения")
        self.confirm_btn.clicked.connect(self.confirm_plan_clicked.emit)
        confirm_row.addWidget(self.confirm_btn)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_plan_clicked.emit)
        confirm_row.addWidget(self.cancel_btn)
        layout.addLayout(confirm_row)
        self.set_confirm_visible(False)

        settings_btn = QPushButton("Настройки")
        settings_btn.clicked.connect(self.open_settings_clicked.emit)
        layout.addWidget(settings_btn)

        self.setWidget(self.main_widget)

    def add_user_message(self, text: str) -> int:
        return self.chat_view.add_user_message(text)

    def add_system_message(self, text: str) -> int:
        return self.chat_view.add_system_message(text)

    def add_assistant_preface(self, text: str) -> int:
        return self.chat_view.add_assistant_preface(text)

    def add_result_message(self, text: str) -> int:
        return self.chat_view.add_result_message(text)

    def add_tool_message(self, text: str) -> int:
        return self.chat_view.add_tool_message(text)

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        self.chat_view.mark_tool_done(message_id, ok)

    def start_model_stream(self) -> int:
        return self.chat_view.start_model_stream()

    def append_model_chunk(self, message_id: int, chunk: str) -> None:
        self.chat_view.append_model_chunk(message_id, chunk)

    def finalize_model_message(self, message_id: int, text: str) -> None:
        self.chat_view.finalize_model_message(message_id, text)

    def finalize_model_plan(self, message_id: int, plan_lines: list[str]) -> None:
        self.chat_view.finalize_model_plan(message_id, plan_lines)

    def add_plan_message(self, plan_lines: list[str]) -> int:
        return self.chat_view.add_plan_message(plan_lines)

    def mark_plan_completed(self, message_id: int) -> None:
        self.chat_view.mark_plan_completed(message_id)

    def set_confirm_visible(self, visible: bool) -> None:
        """Кнопки применения показываются только при накопленном батче изменений."""
        self.confirm_btn.setVisible(visible)
        self.cancel_btn.setVisible(visible)

    def set_busy(self, busy: bool) -> None:
        self.send_btn.setEnabled(not busy)
        if busy:
            self.busy_label.setText("Работаю…")
        else:
            self.busy_label.setText("")

    def _on_create_from_prompt(self):
        prompt = self.prompt_edit.toPlainText().strip()
        self.create_layout_from_prompt_clicked.emit(prompt)
