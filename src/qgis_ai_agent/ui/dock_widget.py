from typing import Callable

from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui import style
from qgis_ai_agent.ui.composer import Composer
from qgis_ai_agent.ui.conversation import ConversationView

TITLE = "QGIS AI Agent"
SETTINGS_ICON = "/mActionOptions.svg"
CLEAR_ICON = "/mActionDeleteSelected.svg"
SESSIONS_ICON = "/mIconQueryHistory.svg"
NEW_SESSION_LABEL = "Новый диалог"
NO_SESSIONS_LABEL = "Прошлых диалогов нет"
HEADER_MARGINS = (11, 8, 9, 8)
HEADER_ICON = 15
HEADER_BUTTON = 24
BODY_MARGINS = (9, 0, 9, 9)


class AgentDockWidget(QDockWidget):
    open_settings_clicked = pyqtSignal()
    new_session_clicked = pyqtSignal()
    session_chosen = pyqtSignal(str)
    prompt_submitted = pyqtSignal(str)
    stop_clicked = pyqtSignal()
    confirm_plan_clicked = pyqtSignal()
    cancel_plan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self._sessions_provider: Callable[[], list[tuple[str, str]]] = list
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self._build_conversation(), 1)
        column.addWidget(self._build_composer())
        self.setWidget(body)

    def _build_header(self) -> QWidget:
        header = QWidget()
        palette = self.palette()
        header.setStyleSheet(
            f"border-bottom: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        )
        row = QHBoxLayout(header)
        row.setContentsMargins(*HEADER_MARGINS)
        row.setSpacing(4)

        title = QLabel(TITLE)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("border: none;")
        row.addWidget(title, 1)
        self._sessions_button = self._build_action(
            SESSIONS_ICON, "⟲", "Диалоги", self._show_sessions
        )
        row.addWidget(self._sessions_button)
        row.addWidget(self._build_action(CLEAR_ICON, "⌫", "Очистить диалог", self._on_clear))
        row.addWidget(
            self._build_action(SETTINGS_ICON, "⚙", "Настройки", self.open_settings_clicked.emit)
        )
        return header

    def _build_action(
        self, icon_name: str, glyph: str, tooltip: str, handler: Callable[[], None]
    ) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setFixedSize(HEADER_BUTTON, HEADER_BUTTON)
        button.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f"color: {style.css_color(style.muted(self.palette()))}; font-size: 14px; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(self.palette()))};"
            "border-radius: 5px; }"
        )
        icon = style.theme_icon(icon_name)
        if icon.isNull():
            button.setText(glyph)
        else:
            button.setIcon(icon)
            button.setIconSize(QSize(HEADER_ICON, HEADER_ICON))
        button.clicked.connect(handler)
        return button

    def _build_conversation(self) -> QWidget:
        self.conversation = ConversationView()
        self.conversation.confirm_requested.connect(self.confirm_plan_clicked.emit)
        self.conversation.cancel_requested.connect(self.cancel_plan_clicked.emit)
        return self.conversation

    def _build_composer(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(*BODY_MARGINS)
        self.composer = Composer()
        self.composer.submitted.connect(self.prompt_submitted.emit)
        self.composer.stopped.connect(self.stop_clicked.emit)
        layout.addWidget(self.composer)
        return holder

    def _on_clear(self) -> None:
        self.conversation.clear()

    def set_session_source(self, provider: Callable[[], list[tuple[str, str]]]) -> None:
        self._sessions_provider = provider

    def _show_sessions(self) -> None:
        menu = QMenu(self)
        fresh = menu.addAction(NEW_SESSION_LABEL)
        menu.addSeparator()
        actions: dict[object, str] = {}
        for identifier, title in self._sessions_provider():
            actions[menu.addAction(title)] = identifier
        if not actions:
            menu.addAction(NO_SESSIONS_LABEL).setEnabled(False)
        button = self._sessions_button
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is fresh:
            self.new_session_clicked.emit()
        elif chosen in actions:
            self.session_chosen.emit(actions[chosen])

    def replay(self, messages: list[dict[str, str]]) -> None:
        self.conversation.clear()
        for message in messages:
            if message.get("role") == "user":
                self.conversation.add_user_message(message.get("content", ""))
            else:
                self.conversation.add_assistant_message(message.get("content", ""))

    def add_user_message(self, text: str) -> int:
        return self.conversation.add_user_message(text)

    def add_system_message(self, text: str) -> int:
        return self.conversation.add_system_message(text)

    def add_result_message(self, text: str) -> int:
        return self.conversation.add_assistant_message(text)

    def add_tool_message(self, text: str) -> int:
        return self.conversation.add_activity_step(text)

    def add_rejected_message(self, text: str) -> int:
        return self.conversation.add_rejected_step(text)

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        self.conversation.mark_activity_step(message_id, ok)

    def add_plan_message(self, plan_lines: list[str]) -> int:
        return self.conversation.add_plan_card(plan_lines)

    def mark_plan_completed(self, message_id: int) -> None:
        self.conversation.mark_plan_applied(message_id)

    def mark_plan_cancelled(self, message_id: int) -> None:
        self.conversation.mark_plan_cancelled(message_id)

    def set_busy(self, busy: bool) -> None:
        self.composer.set_busy(busy)

    def clear_prompt(self) -> None:
        self.composer.clear()
