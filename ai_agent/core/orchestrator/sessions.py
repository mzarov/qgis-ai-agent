"""Conversations: start a new one, pick a past one, and what a switch does to running work."""

from ai_agent.core.orchestrator.notices import SESSION_MISSING, SWITCH_WHILE_APPLYING


class SessionsMixin:
    def on_new_session(self) -> None:
        if self._busy_with_current():
            return
        self.conversation.start_new()
        self._replay()

    def on_session_chosen(self, identifier: str) -> None:
        if self._busy_with_current():
            return
        if not self.conversation.restore(identifier):
            self.dock_widget.add_system_message(SESSION_MISSING)
            return
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
        self.dock_widget.replay(self.conversation.messages)
        self.compaction.refresh()
