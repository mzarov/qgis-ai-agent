import time

from qgis.core import Qgis
from qgis.PyQt.QtCore import QTimer

from ai_agent.core.agent.failures import explain_failure
from ai_agent.core.agent.quick_check import confirmed_by_reading
from ai_agent.core.agent.transcript import StepOutcome, ToolResult
from ai_agent.core.agent.verification import plan_verification
from ai_agent.core.llm.turns import ToolCall
from ai_agent.core.orchestrator.contracts import OrchestratorHost
from ai_agent.core.orchestrator.notices import (
    CHECKED_BY_READING,
    DESTRUCTIVE_DECLINED,
    MODE_NEXT_REQUEST,
    PLAN_DROPPED,
    PLAN_GONE,
    RUN_CHECK,
    RUN_LOOK_INTO,
    RUN_THE_PLAN,
    RUN_THE_PLAN_FOR,
    RUN_THE_PLAN_MODEL,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_HIDDEN,
    STEP_DONE,
    STEP_FAILED,
    STEP_SKIPPED,
    SWITCH_WHILE_RUNNING,
)
from ai_agent.core.orchestrator.planning import destructive_lines, plan_layer, plan_line
from ai_agent.core.orchestrator.presentation import applied_summary, where_to_look
from ai_agent.core.orchestrator.scope import conversation_scope
from ai_agent.core.settings import get_verify_after_apply, set_work_mode
from ai_agent.core.state.trace import APPLIED, CANCELLED, FAILED, PENDING
from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.project.snapshots import last_snapshot

TIME_FORMAT = "%H:%M"


class PlanMixin(OrchestratorHost):
    def on_confirm_needed(self, calls: list[ToolCall], final_text: str, applies_itself: bool = False) -> None:
        if final_text:
            self._render_answer(final_text)
        lines = [self._plan_line(call) for call in calls]
        layer = plan_layer(calls)
        self.dock_widget.show_outcome(STATUS_HIDDEN)
        self._plan_message_id = self.dock_widget.add_plan_message(lines, applies_itself, layer)
        self._plan_keys[self._plan_message_id] = self.conversation.add_plan(lines, layer)
        self._plan_marks = []
        self._plan_step = -1
        if applies_itself:
            QTimer.singleShot(0, self.on_confirm_plan)

    def on_run_plan(self, mode: str) -> None:
        busy = (
            self.agent.is_running
            or self.agent.is_awaiting_answer
            or bool(getattr(self.agent, "is_applying", False))
            or self.compaction.is_running
        )
        if busy:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if not self._confirm_first_send():
            return
        set_work_mode(mode)
        self.dock_widget.set_work_mode(mode)
        request = self._last_request
        prompt = RUN_THE_PLAN_FOR.format(request) if request else RUN_THE_PLAN_MODEL
        self._start_run(RUN_THE_PLAN, prompt, request)

    def on_work_mode(self, mode: str) -> None:
        set_work_mode(mode)
        if self.agent.is_running:
            self.dock_widget.add_system_message(MODE_NEXT_REQUEST)

    @staticmethod
    def _plan_line(call: ToolCall) -> str:
        return plan_line(call)

    def on_confirm_plan(self) -> None:
        if self.compaction.is_running:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if not self.agent.has_pending_writes:
            self.dock_widget.add_system_message(tr("There are no changes to apply."))
            return
        destructive, details = self._destructive_lines()
        if destructive and not self.dock_widget.confirm_destructive(destructive, details):
            self.dock_widget.add_system_message(DESTRUCTIVE_DECLINED)
            return
        self._apply_scope = conversation_scope(self.conversation)
        self._note_apply_start()
        self.dock_widget.begin_work()
        self.agent.confirm_pending()

    def _destructive_lines(self) -> tuple[list[str], str]:
        return destructive_lines(self.agent.pending_writes())

    def on_cancel_plan(self) -> None:
        self.agent.cancel_pending()
        if self._plan_message_id is not None:
            self.dock_widget.mark_plan_cancelled(self._plan_message_id, restorable=True)
            self._plan_settled(CANCELLED)
            self._restorable_plan_id = self._plan_message_id
        self._plan_message_id = None
        if self._retry_after_plan and self.is_idle:
            self._retry_after_plan = False
            self.dock_widget.offer_retry()

    def on_restore_plan(self, message_id: int) -> None:
        restorable = message_id == self._restorable_plan_id and self.is_idle
        if not (restorable and self.agent.restore_declined()):
            self._forget_restore()
            self.dock_widget.add_system_message(PLAN_GONE)
            return
        self._restorable_plan_id = None
        self._plan_message_id = message_id
        self._plan_marks = []
        self._plan_step = -1
        self.dock_widget.mark_plan_restored(message_id)
        self._plan_settled(PENDING, marks=[])

    def _forget_restore(self) -> None:
        if self._restorable_plan_id is not None:
            self.dock_widget.forget_plan_restore(self._restorable_plan_id)
        self._restorable_plan_id = None
        self.agent.forget_declined()

    def _plan_settled(self, state: str, marks: list[list[str]] | None = None, plan_id: int | None = None) -> None:
        card = self._plan_message_id if plan_id is None else plan_id
        key = self._plan_keys.get(card) if card is not None else None
        if not key:
            return
        changes: dict[str, object] = {"state": state, "at": time.strftime(TIME_FORMAT)}
        if marks is not None:
            changes["marks"] = marks
        self.conversation.update_plan(key, **changes)

    def _close_plan_card(self, results: list[ToolResult], failed: bool) -> None:
        self._apply_scope = None
        undoable = self._keep_plan_snapshot()
        self._settle_plan_steps(results)
        if self._plan_message_id is not None:
            if failed:
                self.dock_widget.mark_plan_failed(self._plan_message_id, undoable)
            else:
                self.dock_widget.mark_plan_completed(self._plan_message_id, undoable)
            self._plan_settled(FAILED if failed else APPLIED, self._plan_marks)
        self._plan_message_id = None

    def on_stage_applied(self, results: list[ToolResult]) -> None:
        self._close_plan_card(results, any(not result.ok for result in results))
        self._show_visuals(results)

    def on_applied(self, results: list[ToolResult]) -> None:
        failed = [result for result in results if not result.ok]
        self.usage.note("applies")
        self._close_plan_card(results, bool(failed))
        self._done_summary = "" if failed else applied_summary(results)
        self.dock_widget.show_outcome(STATUS_FAILED if failed else STATUS_DONE, self._done_summary)
        if failed:
            outcome = tr_n("%n step(s) did not run — the reasons are in the plan above.", len(failed))
            self.dock_widget.add_system_message(outcome)
            details = "; ".join(result.error for result in failed)
            self.conversation.add("assistant", f"{outcome}\n{details}")
            self._push_message(tr("Not all changes were applied."), Qgis.MessageLevel.Warning)
        else:
            outcome = tr_n("Done: %n step(s) applied.{0}", len(results)).format(where_to_look(results))
            self.dock_widget.add_result_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Changes applied."), Qgis.MessageLevel.Success)
        self._show_visuals(results)
        self._maybe_verify(results)

    def _show_visuals(self, results: list[ToolResult]) -> None:
        for result in results:
            spec = getattr(result, "visual", None)
            if isinstance(spec, dict):
                self.on_visual_ready(spec)

    def _maybe_verify(self, results: list[ToolResult]) -> None:
        if not results or self.agent.is_running or not get_verify_after_apply():
            return
        if confirmed_by_reading(results):
            self.dock_widget.add_system_message(CHECKED_BY_READING)
            return
        loaded = list(getattr(self.agent, "loaded_skills", None) or [])
        overrides = getattr(self.agent, "overrides", None)
        start = plan_verification(results, self.agent.verification_round, self._last_request, loaded, overrides)
        if start is None or not self._confirm_first_send():
            return
        failed = any(not result.ok for result in results)
        kind = RUN_LOOK_INTO if failed else RUN_CHECK
        self.dock_widget.set_run_kind(kind)
        self.conversation.trace.kind = kind
        self.agent.start(
            start.prompt,
            self.conversation.window(),
            verification=True,
            verification_round=start.round,
            preload=start.preload,
        )

    def _keep_plan_snapshot(self) -> bool:
        before = getattr(self, "_snapshot_before_apply", "")
        self._record_checkpoint()
        taken = last_snapshot()
        if not taken or taken == before or self._plan_message_id is None:
            return False
        self._plan_snapshots[self._plan_message_id] = taken
        return True

    def _settle_plan_steps(self, results: list[ToolResult]) -> None:
        if self._plan_message_id is None:
            return
        self._plan_marks = []
        for index, result in enumerate(results):
            if result.outcome is StepOutcome.SKIPPED:
                state, note = STEP_SKIPPED, ""
            else:
                state, note = (STEP_DONE, "") if result.ok else (STEP_FAILED, explain_failure(result.error))
            self._plan_marks.append([state, note])
            if state != STEP_DONE or index > self._plan_step:
                self.dock_widget.mark_plan_step(self._plan_message_id, index, state, note)

    def _drop_pending_plan(self) -> None:
        pending = self.agent.has_pending_writes
        if pending:
            self.agent.cancel_pending()
            if self._plan_message_id is not None:
                self.dock_widget.mark_plan_cancelled(self._plan_message_id)
                self._plan_settled(CANCELLED)
            self.dock_widget.add_system_message(PLAN_DROPPED)
        self._plan_message_id = None
