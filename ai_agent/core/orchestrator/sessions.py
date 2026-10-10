"""Conversations: start a new one, pick a past one, and what a switch does to running work."""

from ai_agent.core.orchestrator.notices import SESSION_MISSING, SWITCH_WHILE_APPLYING
from ai_agent.core.orchestrator.presentation import project_line


class SessionsMixin:
    def on_new_session(self) -> None:
        if self._busy_with_current():
            return
        kept = bool(self.conversation.messages)
        self.conversation.start_new()
        self._replay()
        if kept:
            self.dock_widget.note_conversation_saved()

    def on_session_chosen(self, identifier: str) -> None:
        if self._busy_with_current():
            return
        if not self.conversation.restore(identifier):
            self.dock_widget.add_system_message(SESSION_MISSING)
            return
        self._replay()

    def on_session_renamed(self, identifier: str, title: str) -> None:
        self.conversation.rename(identifier, title)
        if identifier == self.conversation.session_identifier:
            self._show_title()

    def on_session_deleted(self, identifier: str) -> None:
        if identifier == self.conversation.session_identifier and self._busy_with_current():
            return
        if self.conversation.delete(identifier):
            self._replay()

    def _busy_with_current(self) -> bool:
        self.compaction.cancel()
        if bool(getattr(self.agent, "is_applying", False)):
            self.dock_widget.add_system_message(SWITCH_WHILE_APPLYING)
            return True
        if self.agent.is_running or self.agent.is_awaiting_answer or self.agent.has_pending_writes:
            self.agent.abort()
            self._plan_message_id = None
        return False

    def _replay(self) -> None:
        self._plan_message_id = None
        self._active_tool_message_id = None
        # The replay draws no plan cards, and their ids are the view's: nothing is left to undo from a card.
        self._plan_snapshots.clear()
        self._plan_keys.clear()
        self.dock_widget.set_project_line(project_line())
        self.dock_widget.replay(self.conversation.replayable())
        self._show_title()
        self.compaction.refresh()
