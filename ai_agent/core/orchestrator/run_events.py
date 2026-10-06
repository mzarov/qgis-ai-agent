"""Run events drawn into the chat: tool steps, plan updates, answers, failures and stops."""

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.orchestrator.notices import APPLY_STOPPED, AWAITING_ANSWER, LOG_TAG, RUN_STOPPED
from ai_agent.i18n import tr
from ai_agent.qgis_tools.call_summary import CallSummary


class RunEventsMixin:
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
        self._keep_partial_answer()
        # A stop is deliberate: the request stays in the chat but not back in the box (the user's call).
        self.dock_widget.add_system_message(APPLY_STOPPED if applying else RUN_STOPPED)

    def on_visual_ready(self, spec: dict) -> None:
        self.dock_widget.add_visual(spec)
        self.conversation.add_visual(spec)

    def on_preamble(self, text: str) -> None:
        self._render_answer(text)

    def on_question_asked(self, question: str) -> None:
        self.dock_widget.add_result_message(question)
        self.conversation.add("assistant", question)
        self.dock_widget.add_system_message(AWAITING_ANSWER)

    def on_tool_started(self, summary: str) -> None:
        self._active_tool_message_id = self.dock_widget.add_tool_message(summary)

    def on_tool_finished(self, tool_name: str, ok: bool) -> None:
        if self._active_tool_message_id is not None:
            self.dock_widget.mark_tool_done(self._active_tool_message_id, ok)
            self._active_tool_message_id = None
        if not ok:
            QgsMessageLog.logMessage(f"Tool {tool_name} failed.", LOG_TAG, Qgis.MessageLevel.Warning)

    def on_tool_queued(self, _summary: str) -> None:
        QgsMessageLog.logMessage("A validated step was added to the plan.", LOG_TAG, Qgis.MessageLevel.Info)

    def on_tool_rejected(self, summary: str) -> None:
        self.dock_widget.add_rejected_message(CallSummary.of(tr("Rejected: {0}"), summary))

    def on_plan_changed(self, steps: list, done: int) -> None:
        shown = " · ".join(f"✓ {step}" if index < done else step for index, step in enumerate(steps))
        self.dock_widget.add_tool_message(tr("Plan {0}/{1}: {2}").format(done, len(steps), shown))

    def on_skill_loaded(self, name: str) -> None:
        self.dock_widget.add_tool_message(CallSummary.of(tr("Loading knowledge: {0}"), name))

    def on_journal_written(self, path: str) -> None:
        self.dock_widget.add_system_message(tr("Run journal: {0}").format(path))

    def on_finished(self, text: str) -> None:
        message = (text or "").strip()
        if not message:
            self.dock_widget.add_system_message(tr("The model returned nothing. Try rephrasing."))
            return
        self._render_answer(message)
        self.naming.after_answer()
        if getattr(self.agent, "is_planning", False) and not getattr(self.agent, "ended_on_limit", False):
            # Plan mode ends on a plan: offer to run it, as Claude Code does.
            self.dock_widget.offer_plan()

    def _render_answer(self, message: str) -> None:
        if not self.dock_widget.finish_stream(message):
            self.dock_widget.add_result_message(message)
        self.conversation.add("assistant", message)

    def on_failed(self, message: str) -> None:
        self._active_tool_message_id = None
        self._plan_message_id = None
        self._keep_partial_answer()
        self.dock_widget.add_system_message(tr("Error: {0}").format(message))
        self._push_message(message, Qgis.MessageLevel.Critical)
        self._offer_request_again()

    def _keep_partial_answer(self) -> None:
        partial = self.dock_widget.keep_stream()
        if isinstance(partial, str) and partial:
            self.conversation.add("assistant", partial)

    def _offer_request_again(self) -> None:
        if self._last_request and not getattr(self.agent, "is_verification", False):
            self.dock_widget.restore_prompt(self._last_request)
