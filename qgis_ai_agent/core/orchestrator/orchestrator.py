from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.agent.prompts import build_verification_prompt
from qgis_ai_agent.core.llm.client import is_local
from qgis_ai_agent.core.orchestrator.contracts import DockWidgetContract
from qgis_ai_agent.core.settings import get_api_key, get_api_url, get_verify_after_apply
from qgis_ai_agent.core.state.conversation import ConversationState
from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call

LOG_TAG = "QGIS AI Agent"
MESSAGE_DURATION_SEC = 8
SESSION_MISSING = tr("Conversation not found.")
RUN_STOPPED = tr("Run stopped. Any changes the agent had planned were dropped.")
SWITCH_WHILE_RUNNING = tr("Wait for the current task to finish.")
SWITCH_WHILE_PENDING = tr("Apply or cancel the planned changes first.")
VERIFYING = tr("Checking the applied changes…")
MAX_VERIFICATION_ROUNDS = 3
DESTRUCTIVE_DECLINED = tr("Kept everything as it was — the destructive steps were not applied.")
INTERJECTED = tr("Passed to the agent — it will take this into account on its next step.")
PLAN_DROPPED = tr("The planned changes were dropped — they were not applied. Starting over from your message.")
THOUSAND = 1000
TOKENS_LABEL = tr("{0} tokens")


class CoreOrchestrator:
    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.conversation = ConversationState()
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
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
        self.agent.applied.connect(self.on_applied)
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
        self._active_tool_message_id = None
        self._plan_message_id = None
        self.dock_widget.add_system_message(RUN_STOPPED)

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
        if self.agent.is_running:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return True
        if self.agent.has_pending_writes:
            self.dock_widget.add_system_message(SWITCH_WHILE_PENDING)
            return True
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
        if self.agent.is_running:
            self._interject(text)
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
        self.dock_widget.set_usage(TOKENS_LABEL.format(_compact_number(spent)))

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

    def on_tool_queued(self, summary: str) -> None:
        QgsMessageLog.logMessage(f"Added to plan: {summary}", LOG_TAG, Qgis.Info)

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
        lines = [summarize_tool_call(call.name, call.arguments) for call in calls]
        self._plan_message_id = self.dock_widget.add_plan_message(lines)

    def on_confirm_plan(self) -> None:
        if not self.agent.has_pending_writes:
            self.dock_widget.add_system_message(tr("There are no changes to apply."))
            return
        destructive = self._destructive_lines()
        if destructive and not self.dock_widget.confirm_destructive(destructive):
            self.dock_widget.add_system_message(DESTRUCTIVE_DECLINED)
            return
        self.agent.confirm_pending()

    def _destructive_lines(self) -> list[str]:
        lines = []
        for call in self.agent.pending_writes():
            tool = get_tool_by_name(call.name)
            if tool is not None and tool.safety == SAFETY_DESTRUCTIVE:
                lines.append(summarize_tool_call(call.name, call.arguments))
        return lines

    def on_cancel_plan(self) -> None:
        self.agent.cancel_pending()
        if self._plan_message_id is not None:
            self.dock_widget.mark_plan_cancelled(self._plan_message_id)
        self._plan_message_id = None

    def on_applied(self, results: list) -> None:
        failed = [result for result in results if not result.ok]
        if self._plan_message_id is not None and not failed:
            self.dock_widget.mark_plan_completed(self._plan_message_id)
        self._plan_message_id = None
        if failed:
            details = "; ".join(str(result.payload.get("error", "")) for result in failed)
            outcome = tr("Some steps did not run: {0}").format(details)
            self.dock_widget.add_system_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Not all changes were applied."), Qgis.Warning)
        else:
            outcome = tr("Done: {0} step(s) applied.{1}").format(len(results), self._where_to_look(results))
            self.dock_widget.add_result_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message(tr("Changes applied."), Qgis.Success)
        self._maybe_verify(results)

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

    @staticmethod
    def _where_to_look(results: list) -> str:
        names = [
            result.payload.get("result_layer_name") for result in results if result.payload.get("result_layer_name")
        ]
        if names:
            return " " + tr("New layers: {0}.").format(", ".join(f"«{name}»" for name in names))
        if any("outputs" in result.payload for result in results):
            return " " + tr("The result is in the layer panel.")
        return ""

    def _push_message(self, text: str, level) -> None:
        self.iface.messageBar().pushMessage("QGIS AI Agent", text, level=level, duration=MESSAGE_DURATION_SEC)


def _is_configured() -> bool:
    try:
        url = (get_api_url() or "").strip()
        return bool(url) and (bool((get_api_key() or "").strip()) or is_local(url))
    except Exception:
        return False


def _compact_number(value: int) -> str:
    if value < THOUSAND:
        return str(value)
    return f"{value / THOUSAND:.1f}k"
