"""Plans: the card, Apply and Cancel, what an apply reports, and the check that follows it."""

from qgis.core import Qgis
from qgis.PyQt.QtCore import QTimer

from ai_agent.core.agent.batch_apply import SKIPPED_STATUS
from ai_agent.core.agent.failures import explain_failure
from ai_agent.core.agent.quick_check import confirmed_by_reading
from ai_agent.core.agent.verification import plan_verification
from ai_agent.core.orchestrator.notices import (
    CHECKED_BY_READING,
    DESTRUCTIVE_DECLINED,
    LOOKING_INTO_FAILURE,
    MODE_NEXT_REQUEST,
    PLAN_DROPPED,
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
    VERIFYING,
)
from ai_agent.core.orchestrator.planning import destructive_lines, plan_line
from ai_agent.core.orchestrator.presentation import where_to_look
from ai_agent.core.orchestrator.scope import conversation_scope
from ai_agent.core.settings import get_verify_after_apply, set_work_mode
from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.project.snapshots import last_snapshot


class PlanMixin:
    def on_confirm_needed(self, calls: list, final_text: str, applies_itself: bool = False) -> None:
        if final_text:
            self._render_answer(final_text)
        lines = [self._plan_line(call) for call in calls]
        # The plan card asks for the next step now; the status line has nothing to add.
        self.dock_widget.show_outcome(STATUS_HIDDEN)
        self._plan_message_id = self.dock_widget.add_plan_message(lines, applies_itself)
        self._plan_step = -1
        if applies_itself:
            # Pressed for the user once the card is on screen; the same path as the button.
            QTimer.singleShot(0, self.on_confirm_plan)

    def on_run_plan(self, mode: str) -> None:
        """Leave plan mode for `mode` and ask the agent to carry out the plan it just wrote.

        The chat shows the user's words; the model gets them in English with the original
        request, which the check after Apply also needs.
        """
        busy = (
            self.agent.is_running
            or self.agent.is_awaiting_answer
            or bool(getattr(self.agent, "is_applying", False))
            or self.compaction.is_running
        )
        if busy:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
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
    def _plan_line(call) -> str:
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
        self.agent.confirm_pending()

    def _destructive_lines(self) -> tuple[list[str], str]:
        return destructive_lines(self.agent.pending_writes())

    def on_cancel_plan(self) -> None:
        self.agent.cancel_pending()
        if self._plan_message_id is not None:
            self.dock_widget.mark_plan_cancelled(self._plan_message_id)
        self._plan_message_id = None

    def on_stage_applied(self, results: list) -> None:
        self._apply_scope = None
        undoable = self._keep_plan_snapshot()
        self._settle_plan_steps(results)
        if self._plan_message_id is not None:
            if any(not result.ok for result in results):
                self.dock_widget.mark_plan_failed(self._plan_message_id, undoable)
            else:
                self.dock_widget.mark_plan_completed(self._plan_message_id, undoable)
        self._plan_message_id = None

    def on_applied(self, results: list) -> None:
        self._apply_scope = None
        undoable = self._keep_plan_snapshot()
        failed = [result for result in results if not result.ok]
        self._settle_plan_steps(results)
        if self._plan_message_id is not None:
            if failed:
                self.dock_widget.mark_plan_failed(self._plan_message_id, undoable)
            else:
                self.dock_widget.mark_plan_completed(self._plan_message_id, undoable)
        self._plan_message_id = None
        self.dock_widget.show_outcome(STATUS_FAILED if failed else STATUS_DONE)
        if failed:
            # The reasons stand under the failed steps in the card; the model reads the exact errors
            # in the tool results and the check's prompt.
            outcome = tr_n("%n step(s) did not run — the reasons are in the plan above.", len(failed))
            self.dock_widget.add_system_message(outcome)
            # The next request starts from the conversation: it keeps the exact errors for the model.
            details = "; ".join(_error(result) for result in failed)
            self.conversation.add("assistant", f"{outcome}\n{details}")
            self._push_message(tr("Not all changes were applied."), Qgis.MessageLevel.Warning)
        else:
            outcome = tr_n("Done: %n step(s) applied.{0}", len(results)).format(where_to_look(results))
            self.dock_widget.add_result_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Changes applied."), Qgis.MessageLevel.Success)
        self._maybe_verify(results)

    def _maybe_verify(self, results: list) -> None:
        if not results or self.agent.is_running or not get_verify_after_apply():
            return
        if confirmed_by_reading(results):
            self.dock_widget.add_system_message(CHECKED_BY_READING)
            return
        loaded = list(getattr(self.agent, "loaded_skills", None) or [])
        overrides = getattr(self.agent, "overrides", None)
        start = plan_verification(results, self.agent.verification_round, self._last_request, loaded, overrides)
        if start is None:
            return
        failed = any(not result.ok for result in results)
        self.dock_widget.add_system_message(LOOKING_INTO_FAILURE if failed else VERIFYING)
        self.agent.start(
            start.prompt,
            self.conversation.window(),
            verification=True,
            verification_round=start.round,
            preload=start.preload,
        )

    def _keep_plan_snapshot(self) -> bool:
        """Tag the snapshot this apply took and remember it for the card's Undo; False when none was taken."""
        before = getattr(self, "_snapshot_before_apply", "")
        self._record_checkpoint()
        taken = last_snapshot()
        if not taken or taken == before or self._plan_message_id is None:
            return False
        self._plan_snapshots[self._plan_message_id] = taken
        return True

    def _settle_plan_steps(self, results: list) -> None:
        """Every step's final state on the card, including those that never started."""
        if self._plan_message_id is None:
            return
        for index, result in enumerate(results):
            if result.payload.get("status") == SKIPPED_STATUS:
                state, note = STEP_SKIPPED, ""
            else:
                state, note = (STEP_DONE, "") if result.ok else (STEP_FAILED, explain_failure(_error(result)))
            if state != STEP_DONE or index > self._plan_step:
                self.dock_widget.mark_plan_step(self._plan_message_id, index, state, note)

    def _drop_pending_plan(self) -> None:
        pending = self.agent.has_pending_writes
        if pending:
            self.agent.cancel_pending()
            if self._plan_message_id is not None:
                self.dock_widget.mark_plan_cancelled(self._plan_message_id)
            self.dock_widget.add_system_message(PLAN_DROPPED)
        self._plan_message_id = None


def _error(result: object) -> str:
    return str(getattr(result, "payload", {}).get("error", ""))
