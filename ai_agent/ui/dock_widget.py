from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import confirmations, icons, style
from ai_agent.ui.composer import Composer
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.sessions_popup import SessionsPopup

TITLE = "AI Agent"
HEADER_MARGINS = (11, 8, 9, 8)
HEADER_ICON = 15
HEADER_BUTTON = 24
BODY_MARGINS = (9, 0, 9, 9)
BODY_NAME = "agentBody"


class AgentDockWidget(QDockWidget):
    open_settings_clicked = pyqtSignal()
    new_session_clicked = pyqtSignal()
    session_chosen = pyqtSignal(str)
    session_renamed = pyqtSignal(str, str)
    session_deleted = pyqtSignal(str)
    prompt_submitted = pyqtSignal(str)
    stop_clicked = pyqtSignal()
    confirm_plan_clicked = pyqtSignal()
    cancel_plan_clicked = pyqtSignal()
    files_attached = pyqtSignal(list)
    work_mode_changed = pyqtSignal(str)
    compact_requested = pyqtSignal()
    plan_run_requested = pyqtSignal(str)
    rewind_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self._sessions_provider: Callable[[], list[tuple[str, str]]] = list
        self._sessions_popup = SessionsPopup(self.palette())
        self._sessions_popup.chosen.connect(self.session_chosen.emit)
        self._sessions_popup.renamed.connect(self.session_renamed.emit)
        self._sessions_popup.delete_requested.connect(self._confirm_delete)
        body = QWidget()
        body.setObjectName(BODY_NAME)
        style.fill(body, style.background(self.palette()))
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self._build_conversation(), 1)
        column.addWidget(self._build_composer())
        self.setWidget(body)
        self.composer.set_popup_host(body)

    def _build_header(self) -> QWidget:
        header = QWidget()
        palette = self.palette()
        header.setStyleSheet(f"border-bottom: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};")
        row = QHBoxLayout(header)
        row.setContentsMargins(*HEADER_MARGINS)
        row.setSpacing(4)

        # No title here: the dock's own title bar already says AI Agent; tokens live in the context meter.
        row.addStretch(1)
        self._sessions_button = self._build_action("sessions", "⟲", tr("Conversations"), self._show_sessions)
        row.addWidget(self._sessions_button)
        row.addWidget(self._build_action("clear", "+", tr("New conversation"), self.new_session_clicked.emit))
        row.addWidget(self._build_action("settings", "⚙", tr("Settings"), self.open_settings_clicked.emit))
        return header

    def _build_action(
        self,
        role: str,
        glyph: str,
        tooltip: str,
        handler: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(HEADER_BUTTON, HEADER_BUTTON)
        button.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f"color: {style.css_color(style.muted(self.palette()))}; font-size: 14px; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(self.palette()))};"
            "border-radius: 5px; }"
        )
        icon = icons.drawn(role, style.muted(self.palette()), HEADER_ICON)
        if icon is None:
            button.setText(glyph)
        else:
            button.setIcon(icon)
            button.setIconSize(QSize(HEADER_ICON, HEADER_ICON))
        button.clicked.connect(handler)
        return button

    def set_configured(self, configured: bool) -> None:
        self.conversation.set_configured(configured)
        self.composer.set_configured(configured)

    def set_model(self, name: str) -> None:
        self.composer.set_model(name)

    def _build_conversation(self) -> QWidget:
        self.conversation = ConversationView()
        self.progress = self.conversation.progress
        self.conversation.confirm_requested.connect(self.confirm_plan_clicked.emit)
        self.conversation.plan_run_requested.connect(self.plan_run_requested.emit)
        self.conversation.rewind_requested.connect(self.rewind_requested.emit)
        # A picked answer travels like a typed one: the orchestrator routes it to the waiting run.
        self.conversation.question_answered.connect(self.prompt_submitted.emit)
        self.conversation.cancel_requested.connect(self.cancel_plan_clicked.emit)
        self.conversation.suggestion_chosen.connect(self._on_suggestion)
        self.conversation.settings_requested.connect(self.open_settings_clicked.emit)
        return self.conversation

    def _build_composer(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(*BODY_MARGINS)
        self.composer = Composer()
        self.composer.submitted.connect(self.prompt_submitted.emit)
        self.composer.stopped.connect(self.stop_clicked.emit)
        self.composer.files_attached.connect(self.files_attached.emit)
        self.composer.mode_changed.connect(self.work_mode_changed.emit)
        self.composer.compact_requested.connect(self.compact_requested.emit)
        layout.addWidget(self.composer)
        return holder

    def set_session_source(self, provider: Callable[[], list[tuple[str, str]]]) -> None:
        self._sessions_provider = provider

    def set_skill_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self.composer.set_skill_source(provider)

    def set_layer_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self.composer.set_layer_source(provider)

    def focus_prompt(self) -> None:
        self.composer.focus()

    def restore_prompt(self, text: str) -> None:
        self.composer.restore(text)

    def put_prompt(self, text: str) -> None:
        self.composer.put(text)

    def keep_stream(self) -> str:
        return self.conversation.keep_draft()

    def mention_layers(self, names: list[str]) -> None:
        self.composer.mention_layers(names)

    def add_attachment(self, path: str) -> None:
        self.composer.add_attachment(path)

    def take_attachments(self) -> list[str]:
        return self.composer.take_attachments()

    def _on_suggestion(self, text: str) -> None:
        self.prompt_submitted.emit(text)
        self.composer.focus()

    def _show_sessions(self) -> None:
        # Past conversations only: starting a new one is the button right next to this one.
        self._sessions_popup.show_sessions(self._sessions_provider(), self._sessions_button)

    def _confirm_delete(self, identifier: str, title: str) -> None:
        if confirmations.confirm_delete_conversation(self, title):
            self.session_deleted.emit(identifier)

    def replay(self, messages: list[dict[str, Any]]) -> None:
        self.conversation.clear()
        for index, message in enumerate(messages):
            if message.get("role") == "user":
                entry = self.conversation.add_user_message(message.get("content", ""))
                self.conversation.mark_rewind_point(entry, index)
            elif isinstance(message.get("visual"), dict):
                self.conversation.add_visual(message["visual"])
            else:
                self.conversation.add_assistant_message(message.get("content", ""))

    def add_user_message(self, text: str) -> int:
        return self.conversation.add_user_message(text)

    def mark_rewind_point(self, entry_id: int, message: int) -> None:
        self.conversation.mark_rewind_point(entry_id, message)

    def choose_rewind(self, project_available: bool) -> str | None:
        return confirmations.choose_rewind(self, project_available)

    def add_system_message(self, text: str) -> int:
        return self.conversation.add_system_message(text)

    def add_result_message(self, text: str) -> int:
        return self.conversation.add_assistant_message(text)

    def add_visual(self, spec: dict[str, Any]) -> int:
        return self.conversation.add_visual(spec)

    def add_question(self, question: str, options: list[str]) -> int:
        return self.conversation.add_question(question, options)

    def add_stream_chunk(self, text: str) -> None:
        self.conversation.append_draft(text)

    def add_thinking_chunk(self, text: str) -> None:
        self.conversation.append_thinking(text)

    def finish_stream(self, markdown: str) -> bool:
        return self.conversation.finish_draft(markdown)

    def add_tool_message(self, text: str) -> int:
        self.progress.step(text)
        return self.conversation.add_activity_step(text)

    def add_rejected_message(self, text: str) -> int:
        return self.conversation.add_rejected_step(text)

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        self.conversation.mark_activity_step(message_id, ok)

    def add_plan_message(self, plan_lines: list[str], applies_itself: bool = False) -> int:
        return self.conversation.add_plan_card(plan_lines, applies_itself)

    def set_work_mode(self, mode: str) -> None:
        self.composer.set_mode(mode)

    def offer_plan(self) -> None:
        self.conversation.add_plan_offer()

    def confirm_destructive(self, lines: list[str], details: str = "") -> bool:
        return confirmations.confirm_destructive(self, lines, details)

    def confirm_data_sharing(self, endpoint: str) -> bool:
        return confirmations.confirm_data_sharing(self, endpoint)

    def mark_plan_completed(self, message_id: int) -> None:
        self.conversation.mark_plan_applied(message_id)

    def mark_plan_failed(self, message_id: int) -> None:
        self.conversation.mark_plan_failed(message_id)

    def mark_plan_cancelled(self, message_id: int) -> None:
        self.conversation.mark_plan_cancelled(message_id)

    def set_busy(self, busy: bool) -> None:
        self.composer.set_busy(busy)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()

    def set_context(self, used: int, window: int, spent: int, turns: int = 0) -> None:
        self.composer.set_context(used, window, spent, turns)

    def clear_prompt(self) -> None:
        self.composer.clear()
