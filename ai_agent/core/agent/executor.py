from collections.abc import Callable
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.base import RESULT_IMAGE_KEY, RESULT_VISUAL_KEY
from ai_agent.qgis_tools.registry import execute_tool, get_tool_by_name, start_tool

LOG_TAG = "AI Agent"
UNKNOWN_TOOL_HINT = "Check the list of available tools or load the skill you need."
QUEUED_NOTE = "The action was added to the plan and runs after the user confirms."


class ToolExecutor:
    def run(self, call: ToolCall) -> ToolResult:
        tool = get_tool_by_name(call.name)
        if tool is None:
            return _unknown(call)
        try:
            return self._finished(call, tool, execute_tool(call.name, dict(call.arguments)))
        except Exception as err:
            return self._failed(call, tool, err)

    def start(self, call: ToolCall, done: Callable[[ToolResult], None]) -> Any:
        """Start a call whose tool works off the main thread; `done` gets its result later, on the main thread.

        Returns the running work, whose `cancel` stops it and whose `progressed` reports 0–100,
        or None when the call runs on the main thread: call `run` then. A call that could not
        start runs there too, and `run` reports the same error.
        """
        tool = get_tool_by_name(call.name)
        if tool is None:
            return None
        try:
            work = start_tool(call.name, dict(call.arguments))
        except Exception:
            return None
        if work is None:
            return None

        def ended(outcome: object) -> None:
            if isinstance(outcome, BaseException):
                done(self._failed(call, tool, outcome))
                return
            try:
                result = self._finished(call, tool, outcome)
            except Exception as err:
                result = self._failed(call, tool, err)
            done(result)

        work.finished.connect(ended)
        work.start()
        return work

    def _failed(self, call: ToolCall, tool: Any, err: BaseException) -> ToolResult:
        QgsMessageLog.logMessage(
            f"Tool {call.name} [{call.id}] failed ({type(err).__name__}).",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )
        return ToolResult.failure(call, str(err), tool.egress)

    def _finished(self, call: ToolCall, tool: Any, payload: Any) -> ToolResult:
        prepared = self._as_dict(payload)
        image = str(prepared.pop(RESULT_IMAGE_KEY, "") or "")
        visual = prepared.pop(RESULT_VISUAL_KEY, None)
        if image:
            prepared["image_attached"] = True
        ok = not bool(prepared.get("error"))
        if ok:
            QgsMessageLog.logMessage(f"Tool {call.name} finished.", LOG_TAG, Qgis.MessageLevel.Info)
        else:
            QgsMessageLog.logMessage(f"Tool {call.name} reported a failure.", LOG_TAG, Qgis.MessageLevel.Warning)
        shown = visual if ok and isinstance(visual, dict) else None
        return ToolResult(call=call, ok=ok, payload=prepared, image=image, egress=tool.egress, visual=shown)

    @staticmethod
    def queued(call: ToolCall) -> ToolResult:
        return ToolResult(
            call=call,
            ok=True,
            payload={"status": "queued", "note": QUEUED_NOTE},
        )

    @staticmethod
    def _as_dict(payload: Any) -> dict[str, Any]:
        return dict(payload) if isinstance(payload, dict) else {"result": payload}


def _unknown(call: ToolCall) -> ToolResult:
    return ToolResult(
        call=call,
        ok=False,
        payload={
            "error": f"Unknown tool: {call.name}.",
            "hint": UNKNOWN_TOOL_HINT,
        },
    )
