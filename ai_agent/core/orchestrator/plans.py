"""Plans: the card, Apply and Cancel, what an apply reports, and the check that follows it."""

from qgis.core import Qgis
from qgis.PyQt.QtCore import QTimer

from ai_agent.core.agent.quick_check import confirmed_by_reading
from ai_agent.core.agent.verification import plan_verification
from ai_agent.core.orchestrator.notices import (
    CHECKED_BY_READING,
    DESTRUCTIVE_DECLINED,
    MODE_NEXT_REQUEST,
    PLAN_DROPPED,
    RUN_THE_PLAN,
    RUN_THE_PLAN_FOR,
    RUN_THE_PLAN_MODEL,
    SWITCH_WHILE_RUNNING,
    VERIFYING,
)
from ai_agent.core.orchestrator.planning import destructive_lines, plan_line
from ai_agent.core.orchestrator.presentation import where_to_look
from ai_agent.core.orchestrator.scope import conversation_scope
from ai_agent.core.settings import get_verify_after_apply, set_work_mode
from ai_agent.i18n import tr, tr_n


class PlanMixin:
    def on_confirm_needed(self, calls: list, final_text: str, applies_itself: bool = False) -> None:
        if final_text:
            self._render_answer(final_text)
        lines = [self._plan_line(call) for call in calls]
        self._plan_message_id = self.dock_widget.add_plan_message(lines, applies_itself)
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
        self.dock_widget.add_system_message(VERIFYING)
        self.agent.start(
            start.prompt,
            self.conversation.window(),
            verification=True,
            verification_round=start.round,
            preload=start.preload,
        )

    def _drop_pending_plan(self) -> None:
        pending = self.agent.has_pending_writes
        if pending:
            self.agent.cancel_pending()
            if self._plan_message_id is not None:
                self.dock_widget.mark_plan_cancelled(self._plan_message_id)
            self.dock_widget.add_system_message(PLAN_DROPPED)
        self._plan_message_id = None
