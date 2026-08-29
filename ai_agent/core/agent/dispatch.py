from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent import notices
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.prompts import (
    APPLY_NOW_TOOL,
    ASK_USER_TOOL,
    LOAD_SKILL_TOOL,
    UPDATE_PLAN_TOOL,
)
from ai_agent.core.agent.skills import load_skill
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ToolCall
from ai_agent.core.privacy import tool_output_allowed
from ai_agent.qgis_tools.base import SAFETY_READ, effective_safety, has_network_access
from ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call

LOG_TAG = "AI Agent"


class DispatchMixin:
    def _dispatch(self, call: ToolCall) -> ToolResult:
        if call.name == LOAD_SKILL_TOOL:
            return self._load_skill(call)
        if call.name == UPDATE_PLAN_TOOL:
            return self._update_plan(call)
        if call.name == APPLY_NOW_TOOL:
            return self._request_stage(call)
        if call.name == ASK_USER_TOOL:
            return self._take_question(call)
        tool = get_tool_by_name(call.name)
        if tool is not None and not tool_output_allowed(tool, self.endpoint):
            self.tool_rejected.emit(summarize_tool_call(call.name, call.arguments))
            return ToolResult.failure(call, notices.SENSITIVE_DATA_BLOCKED)
        if tool is None:
            return self._run_now(call)
        if effective_safety(tool, call.arguments) == SAFETY_READ and not has_network_access(tool, call.arguments):
            return self._run_now(call)
        return self._queue_write(call)

    def _run_now(self, call: ToolCall) -> ToolResult:
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
        result = self._executor.run(call)
        self.tool_finished.emit(call.name, result.ok)
        return result

    def _queue_write(self, call: ToolCall) -> ToolResult:
        try:
            queued = self._batch.add(call)
        except Exception as err:
            self.tool_rejected.emit(summarize_tool_call(call.name, call.arguments))
            QgsMessageLog.logMessage(
                f"Step {call.name} [{call.id}] rejected ({type(err).__name__}).",
                LOG_TAG,
                Qgis.Warning,
            )
            return ToolResult.failure(call, str(err))
        tool = get_tool_by_name(queued.name)
        if tool is not None and effective_safety(tool, queued.arguments) == SAFETY_READ:
            self._staged = self._staged or has_network_access(tool, queued.arguments)
        self.tool_queued.emit(summarize_tool_call(queued.name, queued.arguments))
        return ToolExecutor.queued(queued)

    def _take_question(self, call: ToolCall) -> ToolResult:
        question = str(call.arguments.get("question") or "").strip()
        if not question:
            return ToolResult.failure(call, "The question is empty — say what you need to know.")
        self._question = question
        return ToolResult(call=call, ok=True, payload={"status": "waiting_for_user"})

    def answer(self, text: str) -> bool:
        reply = (text or "").strip()
        if not reply or not self._question:
            return False
        self._question = ""
        self._transcript.add_user(reply)
        self.busy_changed.emit(True)
        self._request_step()
        return True

    def _request_stage(self, call: ToolCall) -> ToolResult:
        if not self._batch:
            return ToolResult.failure(call, notices.APPLY_NOW_WITHOUT_WRITES)
        if self._staged:
            if self._stage_call is None:
                self._stage_call = call
                return ToolResult(call=call, ok=True, payload={"status": "awaiting_user"})
            return ToolResult.failure(call, "Apply has already been requested for this stage.")
        self._staged = True
        self._stage_call = call
        return ToolResult(call=call, ok=True, payload={"status": "awaiting_user"})

    def _update_plan(self, call: ToolCall) -> ToolResult:
        raw_steps = call.arguments.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult.failure(call, "steps must be a non-empty list of short strings.")
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
        try:
            done = max(0, min(len(steps), int(call.arguments.get("done") or 0)))
        except (TypeError, ValueError):
            done = 0
        self._plan_steps = steps
        self._plan_done = done
        self.plan_changed.emit(list(steps), done)
        return ToolResult(call=call, ok=True, payload={"steps": len(steps), "done": done})

    def _load_skill(self, call: ToolCall) -> ToolResult:
        result, loaded = load_skill(call, self._loaded_skills)
        if loaded:
            self.skill_loaded.emit(loaded)
            QgsMessageLog.logMessage(f"Skill loaded: {loaded}.", LOG_TAG, Qgis.Info)
        return result
