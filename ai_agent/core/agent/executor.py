from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.base import RESULT_IMAGE_KEY
from ai_agent.qgis_tools.registry import execute_tool, get_tool_by_name

LOG_TAG = "AI Agent"
UNKNOWN_TOOL_HINT = "Check the list of available tools or load the skill you need."
QUEUED_NOTE = "The action was added to the plan and runs after the user confirms."


class ToolExecutor:
    def run(self, call: ToolCall) -> ToolResult:
        tool = get_tool_by_name(call.name)
        if tool is None:
            return ToolResult(
                call=call,
                ok=False,
                payload={
                    "error": f"Unknown tool: {call.name}.",
                    "hint": UNKNOWN_TOOL_HINT,
                },
            )
        try:
            payload = execute_tool(call.name, dict(call.arguments))
            prepared = self._as_dict(payload)
            image = str(prepared.pop(RESULT_IMAGE_KEY, "") or "")
            if image:
                prepared["image_attached"] = True
            ok = not bool(prepared.get("error"))
        except Exception as err:
            QgsMessageLog.logMessage(
                f"Tool {call.name} [{call.id}] failed ({type(err).__name__}).",
                LOG_TAG,
                Qgis.MessageLevel.Warning,
            )
            return ToolResult.failure(call, str(err), tool.egress)
        if ok:
            QgsMessageLog.logMessage(f"Tool {call.name} finished.", LOG_TAG, Qgis.MessageLevel.Info)
        else:
            QgsMessageLog.logMessage(f"Tool {call.name} reported a failure.", LOG_TAG, Qgis.MessageLevel.Warning)
        return ToolResult(call=call, ok=ok, payload=prepared, image=image, egress=tool.egress)

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
