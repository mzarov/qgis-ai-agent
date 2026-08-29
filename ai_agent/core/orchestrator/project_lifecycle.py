from ai_agent.core.orchestrator.scope import conversation_scope
from ai_agent.i18n import tr

PROJECT_CHANGED = tr("The QGIS project changed. A new project-scoped conversation was started.")
PREVIOUS_APPLY_INTERRUPTED = tr("An interrupted run completed work in the previous project; see its conversation.")
UNDO_TOOL = "undo_last_apply"
__all__ = ("PREVIOUS_APPLY_INTERRUPTED", "PROJECT_CHANGED", "ProjectLifecycleMixin")


class ProjectLifecycleMixin:
    def on_project_changed(self, force_new: bool = False) -> None:
        if not force_new and getattr(self.agent, "active_apply_tool", "") == UNDO_TOOL:
            return
        if not self.conversation.sync_project(force_new):
            return
        self._abort_project_work()
        self._replay()
        self.dock_widget.add_system_message(PROJECT_CHANGED)
        if self._deferred_interrupted_outcome:
            self._show_previous_apply(self._deferred_interrupted_outcome)
        self._deferred_interrupted_outcome = ""
        self._invalidated_scope = None

    def on_project_cleared(self) -> bool:
        if getattr(self.agent, "active_apply_tool", "") == UNDO_TOOL:
            return False
        self._invalidated_scope = conversation_scope(self.conversation)
        self._abort_project_work()
        return True

    def _abort_project_work(self) -> None:
        if self.agent.is_running or self.agent.has_pending_writes or self.agent.is_awaiting_answer:
            self.agent.abort()

    def _show_previous_apply(self, outcome: str) -> None:
        self.dock_widget.add_system_message(PREVIOUS_APPLY_INTERRUPTED)
        self.dock_widget.add_system_message(outcome)
