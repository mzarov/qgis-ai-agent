from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.prompts import build_verification_prompt
from ai_agent.core.orchestrator.contracts import DockWidgetContract
from ai_agent.core.orchestrator.planning import destructive_lines, plan_line
from ai_agent.core.orchestrator.presentation import compact_number, interrupted_outcome, is_configured, where_to_look
from ai_agent.core.orchestrator.project_lifecycle import (
    PREVIOUS_APPLY_INTERRUPTED,
    PROJECT_CHANGED,
    ProjectLifecycleMixin,
)
from ai_agent.core.orchestrator.scope import conversation_scope
from ai_agent.core.settings import (
    get_verify_after_apply,
)
from ai_agent.core.state.conversation import ConversationState
from ai_agent.i18n import tr, tr_n

LOG_TAG = "AI Agent"
MESSAGE_DURATION_SEC = 8
SESSION_MISSING = tr("Conversation not found.")
RUN_STOPPED = tr("Run stopped. Pending work was cancelled.")
APPLY_STOPPED = tr("Run stopped during apply. Pending steps were cancelled; any completed changes remain.")
SWITCH_WHILE_RUNNING = tr("Wait for the current task to finish.")
SWITCH_WHILE_APPLYING = tr("Changes are being applied — wait for that to finish.")
VERIFYING = tr("Checking the applied changes…")
MAX_VERIFICATION_ROUNDS = 3
DESTRUCTIVE_DECLINED = tr("Kept everything as it was — the destructive steps were not applied.")
INTERJECTED = tr("Passed to the agent — it will take this into account on its next step.")
PLAN_DROPPED = tr("The planned changes were dropped — they were not applied. Starting over from your message.")
AWAITING_ANSWER = tr("Waiting for your answer — the run continues from it.")
TOKENS_LABEL = tr("{0} tokens")
__all__ = ("CoreOrchestrator", "PREVIOUS_APPLY_INTERRUPTED", "PROJECT_CHANGED")


class CoreOrchestrator(ProjectLifecycleMixin):
    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.conversation = ConversationState()
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
        self._apply_scope: tuple[str, str] | None = None
        self._invalidated_scope: tuple[str, str] | None = None
        self._deferred_interrupted_outcome = ""
        self._connect_agent()
        self.dock_widget.set_session_source(self.conversation.recent)
        self.refresh_configured()

    def refresh_configured(self) -> None:
        self.dock_widget.set_configured(_is_configured())

    def _connect_agent(self) -> None:
        self.agent.tool_started.connect(self.on_tool_started)
        self.agent.tool_finished.connect(self.on_tool_finished)
        self.agent.tool_queued.connect(self.on_tool_queued)
        self.agent.tool_rejected.connect(self.on_tool_rejected)
        self.agent.skill_loaded.connect(self.on_skill_loaded)
        self.agent.plan_changed.connect(self.on_plan_changed)
        self.agent.confirm_needed.connect(self.on_confirm_needed)
        self.agent.question_asked.connect(self.on_question_asked)
        self.agent.preamble.connect(self.on_preamble)
        self.agent.applied.connect(self.on_applied)
        self.agent.stage_applied.connect(self.on_stage_applied)
        self.agent.apply_interrupted.connect(self.on_apply_interrupted)
        self.agent.journal_written.connect(self.on_journal_written)
        self.agent.finished.connect(self.on_finished)
        self.agent.failed.connect(self.on_failed)
        self.agent.aborted.connect(self.on_aborted)
        self.agent.busy_changed.connect(self.dock_widget.set_busy)
        self.agent.usage_changed.connect(self.on_usage_changed)
        self.agent.answer_chunk.connect(self.dock_widget.add_stream_chunk)
        self.agent.thinking_chunk.connect(self.dock_widget.add_thinking_chunk)

    def on_stop(self) -> None:
        self.agent.abort()

    def on_aborted(self) -> None:
        applying = bool(getattr(self.agent, "is_applying", False))
        if self._active_tool_message_id is not None and not applying:
            self.dock_widget.mark_tool_done(self._active_tool_message_id, False)
            self._active_tool_message_id = None
        if self._plan_message_id is not None:
            if applying:
                self.dock_widget.mark_plan_failed(self._plan_message_id)
            else:
                self.dock_widget.mark_plan_cancelled(self._plan_message_id)
        self._plan_message_id = None
        self.dock_widget.add_system_message(APPLY_STOPPED if applying else RUN_STOPPED)

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

    def on_prompt(self, prompt: str) -> None:
        text = (prompt or "").strip()
        if not text:
            self._push_message(tr("Type a request."), Qgis.Warning)
            return
        if bool(getattr(self.agent, "is_applying", False)):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if self.agent.is_running:
            self._interject(text)
            return
        if self.agent.is_awaiting_answer:
            self._answer(text)
            return
        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self._drop_pending_plan()
        self.dock_widget.set_usage("")
        history = self.conversation.window()
        self.conversation.add("user", text)
        self.agent.start(text, history)

    def _drop_pending_plan(self) -> None:
        pending = self.agent.has_pending_writes
        if pending:
            self.agent.cancel_pending()
            if self._plan_message_id is not None:
                self.dock_widget.mark_plan_cancelled(self._plan_message_id)
            self.dock_widget.add_system_message(PLAN_DROPPED)
        self._plan_message_id = None

    def on_usage_changed(self, spent: int) -> None:
        self.dock_widget.set_usage(TOKENS_LABEL.format(compact_number(spent)))

    def on_preamble(self, text: str) -> None:
        self._render_answer(text)

    def on_question_asked(self, question: str) -> None:
        self.dock_widget.add_result_message(question)
        self.conversation.add("assistant", question)
        self.dock_widget.add_system_message(AWAITING_ANSWER)

    def _answer(self, text: str) -> None:
        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self.conversation.add("user", text)
        self.agent.answer(text)

    def _interject(self, text: str) -> None:
        if not self.agent.interject(text):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self.dock_widget.add_system_message(INTERJECTED)
        self.conversation.add("user", text)

    def on_tool_started(self, summary: str) -> None:
        self._active_tool_message_id = self.dock_widget.add_tool_message(summary)

    def on_tool_finished(self, tool_name: str, ok: bool) -> None:
        if self._active_tool_message_id is not None:
            self.dock_widget.mark_tool_done(self._active_tool_message_id, ok)
            self._active_tool_message_id = None
        if not ok:
            QgsMessageLog.logMessage(f"Tool {tool_name} failed.", LOG_TAG, Qgis.Warning)

    def on_tool_queued(self, _summary: str) -> None:
        QgsMessageLog.logMessage("A validated step was added to the plan.", LOG_TAG, Qgis.Info)

    def on_tool_rejected(self, summary: str) -> None:
        self.dock_widget.add_rejected_message(tr("Rejected: {0}").format(summary))

    def on_plan_changed(self, steps: list, done: int) -> None:
        shown = " · ".join(f"✓ {step}" if index < done else step for index, step in enumerate(steps))
        self.dock_widget.add_tool_message(tr("Plan {0}/{1}: {2}").format(done, len(steps), shown))

    def on_skill_loaded(self, name: str) -> None:
        self.dock_widget.add_tool_message(tr("Loading knowledge: {0}").format(name))

    def on_confirm_needed(self, calls: list, final_text: str) -> None:
        if final_text:
            self._render_answer(final_text)
        lines = [self._plan_line(call) for call in calls]
        self._plan_message_id = self.dock_widget.add_plan_message(lines)

    @staticmethod
    def _plan_line(call) -> str:
        return plan_line(call)

    def on_confirm_plan(self) -> None:
        if not self.agent.has_pending_writes:
            self.dock_widget.add_system_message(tr("There are no changes to apply."))
            return
        destructive, details = self._destructive_lines()
        if destructive and not self.dock_widget.confirm_destructive(destructive, details):
            self.dock_widget.add_system_message(DESTRUCTIVE_DECLINED)
            return
        self._apply_scope = conversation_scope(self.conversation)
        self.agent.confirm_pending()

    def _destructive_lines(self) -> tuple[list[str], str]:
        return destructive_lines(self.agent.pending_writes())

    def on_cancel_plan(self) -> None:
        self.agent.cancel_pending()
        if self._plan_message_id is not None:
            self.dock_widget.mark_plan_cancelled(self._plan_message_id)
        self._plan_message_id = None

    def on_journal_written(self, path: str) -> None:
        self.dock_widget.add_system_message(tr("Run journal: {0}").format(path))

    def on_stage_applied(self, results: list) -> None:
        self._apply_scope = None
        if self._plan_message_id is not None:
            if any(not result.ok for result in results):
                self.dock_widget.mark_plan_failed(self._plan_message_id)
            else:
                self.dock_widget.mark_plan_completed(self._plan_message_id)
        self._plan_message_id = None

    def on_applied(self, results: list) -> None:
        self._apply_scope = None
        failed = [result for result in results if not result.ok]
        if self._plan_message_id is not None:
            if failed:
                self.dock_widget.mark_plan_failed(self._plan_message_id)
            else:
                self.dock_widget.mark_plan_completed(self._plan_message_id)
        self._plan_message_id = None
        if failed:
            details = "; ".join(str(result.payload.get("error", "")) for result in failed)
            outcome = tr("Some steps did not run: {0}").format(details)
            self.dock_widget.add_system_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Not all changes were applied."), Qgis.Warning)
        else:
            outcome = tr_n("Done: %n step(s) applied.{0}", len(results)).format(where_to_look(results))
            self.dock_widget.add_result_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Changes applied."), Qgis.Success)
        self._maybe_verify(results)

    def on_apply_interrupted(self, results: list) -> None:
        scope = self._apply_scope
        self._apply_scope = None
        outcome = interrupted_outcome(results)
        if not outcome:
            return
        current_scope = conversation_scope(self.conversation)
        invalidated = scope is not None and scope == self._invalidated_scope
        if scope != current_scope or invalidated:
            if scope is not None:
                self.conversation.add_scoped(scope, "assistant", outcome)
            if invalidated and scope == current_scope:
                self._deferred_interrupted_outcome = outcome
            else:
                self._show_previous_apply(outcome)
            return
        self.dock_widget.add_result_message(outcome)
        self.conversation.add("assistant", outcome)

    def _maybe_verify(self, results: list) -> None:
        if not results or self.agent.is_running or not get_verify_after_apply():
            return
        next_round = self.agent.verification_round + 1
        if next_round > MAX_VERIFICATION_ROUNDS:
            QgsMessageLog.logMessage(
                f"Stopping after {MAX_VERIFICATION_ROUNDS} verification rounds.", LOG_TAG, Qgis.Warning
            )
            return
        outcomes = [
            {"tool": result.call.name, "ok": result.ok, "error": str(result.payload.get("error", ""))}
            for result in results
        ]
        self.dock_widget.add_system_message(VERIFYING)
        self.agent.start(
            build_verification_prompt(outcomes),
            self.conversation.window(),
            verification=True,
            verification_round=next_round,
        )

    def on_finished(self, text: str) -> None:
        message = (text or "").strip()
        if not message:
            self.dock_widget.add_system_message(tr("The model returned nothing. Try rephrasing."))
            return
        self._render_answer(message)

    def _render_answer(self, message: str) -> None:
        if not self.dock_widget.finish_stream(message):
            self.dock_widget.add_result_message(message)
        self.conversation.add("assistant", message)

    def on_failed(self, message: str) -> None:
        self._active_tool_message_id = None
        self._plan_message_id = None
        self.dock_widget.add_system_message(tr("Error: {0}").format(message))
        self._push_message(message, Qgis.Critical)

    def shutdown(self) -> None:
        self.conversation.save()
        self.agent.stop()

    def _push_message(self, text: str, level) -> None:
        self.iface.messageBar().pushMessage("AI Agent", text, level=level, duration=MESSAGE_DURATION_SEC)


def _is_configured() -> bool:
    return is_configured()
