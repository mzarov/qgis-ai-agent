from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.base import RESULT_IMAGE_KEY
from qgis_ai_agent.qgis_tools.registry import execute_tool, get_tool_by_name

LOG_TAG = "QGIS AI Agent"
UNKNOWN_TOOL_HINT = "Check the list of available tools or load the skill you need."
QUEUED_NOTE = "The action was added to the plan and runs after the user confirms."


class ToolExecutor:
    def run(self, call: ToolCall) -> ToolResult:
        if get_tool_by_name(call.name) is None:
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
        except Exception as err:
            QgsMessageLog.logMessage(
                f"Tool {call.name} failed: {err} | arguments: {call.arguments}",
                LOG_TAG,
                Qgis.Warning,
            )
            return ToolResult.failure(call, str(err))
        QgsMessageLog.logMessage(f"Tool {call.name} finished.", LOG_TAG, Qgis.Info)
        prepared = self._as_dict(payload)
        image = str(prepared.pop(RESULT_IMAGE_KEY, "") or "")
        if image:
            prepared["image_attached"] = True
        return ToolResult(call=call, ok=True, payload=prepared, image=image)

    @staticmethod
    def queued(call: ToolCall) -> ToolResult:
        return ToolResult(
            call=call,
            ok=True,
            payload={"status": "queued", "note": QUEUED_NOTE},
        )

    @staticmethod
    def _as_dict(payload: Any) -> dict[str, Any]:
        return payload if isinstance(payload, dict) else {"result": payload}
