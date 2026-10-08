"""The panel: its own title bar, the toolbar, the feed and the composer; the orchestrator's contract."""

import time
from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDockWidget, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import chrome, confirmations, style
from ai_agent.ui.composer import Composer
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.sessions_popup import Entry, SessionsPopup

TITLE = chrome.TITLE
# The handoff's composer padding: 6 above the box, 12 around the rest.
COMPOSER_MARGINS = (12, 6, 12, 12)
BODY_NAME = "agentBody"
NEW_CONVERSATION_TITLE = tr("New conversation")


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
    plan_undo_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Before any child is built: children read the panel's palette, which must already be the theme's.
        style.apply_palette(self)
        self.setWindowTitle(TITLE)
        palette = self.palette()
        self.title_bar = chrome.DockTitleBar(self, palette)
        self.setTitleBarWidget(self.title_bar)
        self._sessions_provider: Callable[[], list[tuple[Any, ...]]] = list
        self._sessions_popup = SessionsPopup(palette)
        self._sessions_popup.chosen.connect(self.session_chosen.emit)
        self._sessions_popup.renamed.connect(self.session_renamed.emit)
        self._sessions_popup.delete_requested.connect(self._confirm_delete)
        self._sessions_popup.new_requested.connect(self.new_session_clicked.emit)
        body = QWidget()
        body.setObjectName(BODY_NAME)
        style.fill(body, style.background(palette))
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.toolbar = chrome.Toolbar(palette)
        self.toolbar.history_requested.connect(self._show_sessions)
        self.toolbar.new_requested.connect(self.new_session_clicked.emit)
        self.toolbar.settings_requested.connect(self.open_settings_clicked.emit)
        self.toolbar.title.set_title(NEW_CONVERSATION_TITLE)
        column.addWidget(self.toolbar)
        column.addWidget(self._build_conversation(), 1)
        column.addWidget(self._build_composer())
        self.setWidget(body)
        self.composer.set_popup_host(body)
        # The welcome is up: there is nothing to start over from yet.
        self.toolbar.new_button.setEnabled(False)

    def set_conversation_title(self, title: str) -> None:
        self.toolbar.title.set_title(title or NEW_CONVERSATION_TITLE)

    def note_conversation_saved(self) -> None:
        self.conversation.show_saved_hint()

    def set_active_layer(self, name: str, detail: str = "") -> None:
        self.composer.set_active_layer(name, detail)

    def context_mention(self) -> str:
        return self.composer.context_mention()

    def set_project_line(self, text: str) -> None:
        self.conversation.set_project_line(text)

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
        self.conversation.plan_undo_requested.connect(self.plan_undo_requested.emit)
        # A picked answer travels like a typed one: the orchestrator routes it to the waiting run.
        self.conversation.question_answered.connect(self.prompt_submitted.emit)
        self.conversation.cancel_requested.connect(self.cancel_plan_clicked.emit)
        self.conversation.suggestion_chosen.connect(self._on_suggestion)
        self.conversation.settings_requested.connect(self.open_settings_clicked.emit)
        self.conversation.history_requested.connect(self._show_sessions)
        self.conversation.emptied.connect(self._on_emptied)
        return self.conversation

    def _on_emptied(self, empty: bool) -> None:
        self.toolbar.new_button.setEnabled(not empty)

    def _build_composer(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(*COMPOSER_MARGINS)
        self.composer = Composer()
        self.composer.submitted.connect(self.prompt_submitted.emit)
        self.composer.stopped.connect(self.stop_clicked.emit)
        self.composer.files_attached.connect(self.files_attached.emit)
        self.composer.mode_changed.connect(self.work_mode_changed.emit)
        self.composer.compact_requested.connect(self.compact_requested.emit)
        self.composer.settings_requested.connect(self.open_settings_clicked.emit)
        self.composer.new_requested.connect(self.new_session_clicked.emit)
        layout.addWidget(self.composer)
        return holder

    def set_session_source(self, provider: Callable[[], list[tuple[Any, ...]]]) -> None:
        """`provider` gives (identifier, title[, updated, current]) tuples, so no core type reaches the ui."""
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
        entries = [Entry(*item) for item in self._sessions_provider()]
        self._sessions_popup.show_sessions(entries, self.toolbar.title, time.time())

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
        return self.conversation.add_activity_step(text)

    def add_rejected_message(self, text: str) -> int:
        return self.conversation.add_rejected_step(text)

    def mark_tool_done(self, message_id: int, ok: bool = True, note: str = "") -> None:
        self.conversation.mark_activity_step(message_id, ok, note)

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

    def mark_plan_completed(self, message_id: int, undoable: bool = False) -> None:
        self.conversation.mark_plan_applied(message_id, undoable)

    def mark_plan_failed(self, message_id: int, undoable: bool = False) -> None:
        self.conversation.mark_plan_failed(message_id, undoable)

    def mark_plan_undone(self, message_id: int) -> None:
        self.conversation.mark_plan_undone(message_id)

    def mark_plan_step(self, message_id: int, index: int, state: str, note: str = "") -> None:
        self.conversation.mark_plan_step(message_id, index, state, note)

    def mark_plan_cancelled(self, message_id: int) -> None:
        self.conversation.mark_plan_cancelled(message_id)

    def show_outcome(self, kind: str) -> None:
        self.progress.show_outcome(kind)

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
