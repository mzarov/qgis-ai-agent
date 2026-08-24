from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.registry import execute_tool, get_tool_by_name

LOG_TAG = "QGIS AI Agent"


class ToolExecutor:
    """
    Выполняет вызовы тулов в главном потоке.
    Ошибка тула не обрывает прогон: она возвращается модели как результат,
    чтобы та могла исправиться сама.
    """

    def run(self, call: ToolCall) -> ToolResult:
        """Выполняет один вызов и всегда возвращает результат, даже при ошибке."""
        tool = get_tool_by_name(call.name)
        if tool is None:
            return ToolResult(
                call=call,
                ok=False,
                payload={
                    "error": f"Неизвестный инструмент: {call.name}.",
                    "hint": "Проверьте список доступных тулов или загрузите нужный скилл.",
                },
            )
        try:
            payload = execute_tool(call.name, dict(call.arguments))
            QgsMessageLog.logMessage(f"Тул {call.name} выполнен.", LOG_TAG, Qgis.Info)
            return ToolResult(call=call, ok=True, payload=self._as_dict(payload))
        except Exception as err:
            # Аргументы в логе — иначе неверный вызов не отладить постфактум.
            QgsMessageLog.logMessage(
                f"Тул {call.name} упал: {err} | аргументы: {call.arguments}",
                LOG_TAG,
                Qgis.Warning,
            )
            return ToolResult(
                call=call,
                ok=False,
                payload={"error": str(err), "arguments_sent": call.arguments},
            )

    @staticmethod
    def queued(call: ToolCall) -> ToolResult:
        """Ответ модели на write-вызов: действие поставлено в очередь на подтверждение."""
        return ToolResult(
            call=call,
            ok=True,
            payload={
                "status": "queued",
                "note": "Действие добавлено в план и будет выполнено после подтверждения пользователя.",
            },
        )

    @staticmethod
    def _as_dict(payload: Any) -> dict[str, Any]:
        """Приводит результат тула к словарю для сериализации."""
        if isinstance(payload, dict):
            return payload
        return {"result": payload}
