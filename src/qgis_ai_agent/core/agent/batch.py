from dataclasses import replace
from typing import Any, Callable

from qgis.PyQt.QtWidgets import QApplication

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.registry import prepare_tool_call


class WriteBatch:
    def __init__(self, executor: ToolExecutor):
        self._executor = executor
        self._calls: list[ToolCall] = []

    def __bool__(self) -> bool:
        return bool(self._calls)

    def clear(self) -> None:
        self._calls = []

    def add(self, call: ToolCall) -> ToolCall:
        prepared = prepare_tool_call(call.name, dict(call.arguments))
        queued = replace(call, arguments=prepared)
        self._calls.append(queued)
        return queued

    def pending(self) -> list[ToolCall]:
        return list(self._calls)

    def apply(
        self,
        on_start: Callable[[ToolCall], Any],
        on_finish: Callable[[ToolCall, ToolResult], Any],
    ) -> list[ToolResult]:
        calls = self._calls
        self._calls = []
        results = []
        for call in calls:
            on_start(call)
            QApplication.processEvents()
            result = self._executor.run(call)
            on_finish(call, result)
            QApplication.processEvents()
            results.append(result)
        return results
