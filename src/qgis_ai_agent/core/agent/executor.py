from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.registry import execute_tool, get_tool_by_name

LOG_TAG = "QGIS AI Agent"
UNKNOWN_TOOL_HINT = "Проверьте список доступных тулов или загрузите нужный скилл."
QUEUED_NOTE = "Действие добавлено в план и будет выполнено после подтверждения пользователя."


class ToolExecutor:
    def run(self, call: ToolCall) -> ToolResult:
        if get_tool_by_name(call.name) is None:
            return ToolResult(
                call=call,
                ok=False,
                payload={
                    "error": f"Неизвестный инструмент: {call.name}.",
                    "hint": UNKNOWN_TOOL_HINT,
                },
            )
        try:
            payload = execute_tool(call.name, dict(call.arguments))
        except Exception as err:
            QgsMessageLog.logMessage(
                f"Тул {call.name} упал: {err} | аргументы: {call.arguments}",
                LOG_TAG,
                Qgis.Warning,
            )
            return ToolResult.failure(call, str(err))
        QgsMessageLog.logMessage(f"Тул {call.name} выполнен.", LOG_TAG, Qgis.Info)
        return ToolResult(call=call, ok=True, payload=self._as_dict(payload))

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
