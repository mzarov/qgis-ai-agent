import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QEventLoop
from qgis.PyQt.QtWidgets import QApplication

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.common.project_identity import project_identity
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, prepare_tool_call

SKIPPED_STATUS = "skipped"
UNDO_TOOL = "undo_last_apply"
PROJECT_CHANGED_ERROR = (
    "The QGIS project changed while this plan was being applied. This step and every later step were stopped."
)


def _signature(call: ToolCall) -> str:
    try:
        arguments = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        arguments = str(sorted(call.arguments.items()))
    return f"{call.name}|{arguments}"


class WriteBatch:
    def __init__(self, executor: ToolExecutor):
        self._executor = executor
        self._calls: list[ToolCall] = []
        self._applying = False
        self._cancel_requested = False

    def __bool__(self) -> bool:
        return bool(self._calls) or self._applying

    @property
    def is_applying(self) -> bool:
        return self._applying

    def clear(self) -> None:
        self._calls = []
        self._cancel_requested = self._applying

    def add(self, call: ToolCall) -> ToolCall:
        if self._applying:
            raise ValueError("Wait for the current plan to finish before adding another change.")
        prepared = prepare_tool_call(call.name, dict(call.arguments))
        queued = replace(call, arguments=prepared)
        if (queued.name == UNDO_TOOL and self._calls) or any(existing.name == UNDO_TOOL for existing in self._calls):
            raise ValueError("Undo must be applied by itself, before planning any other changes.")
        existing = self._same_call(queued)
        if existing is not None:
            return queued
        self._calls.append(queued)
        return queued

    def _same_call(self, queued: ToolCall) -> ToolCall | None:
        signature = _signature(queued)
        for call in self._calls:
            if _signature(call) == signature:
                return call
        return None

    def pending(self) -> list[ToolCall]:
        return list(self._calls)

    def apply(
        self,
        on_start: Callable[[ToolCall], Any],
        on_finish: Callable[[ToolCall, ToolResult], Any],
        expected_project_identity: str | None = None,
    ) -> list[ToolResult]:
        if self._applying:
            raise RuntimeError("This plan is already being applied.")
        calls = self._calls
        self._calls = []
        expected = expected_project_identity or project_identity(QgsProject.instance())
        self._applying = True
        self._cancel_requested = False
        try:
            results = []
            failed: ToolResult | None = None
            for call in calls:
                on_start(call)
                QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
                if failed is not None:
                    result = _skipped_result(call, failed.call)
                elif self._cancel_requested or project_identity(QgsProject.instance()) != expected:
                    result = _project_changed_result(call)
                else:
                    result = self._executor.run(call)
                on_finish(call, result)
                results.append(result)
                if not result.ok and failed is None:
                    failed = result
            return results
        finally:
            self._applying = False
            self._cancel_requested = False


def _skipped_result(call: ToolCall, blocker: ToolCall) -> ToolResult:
    tool = get_tool_by_name(call.name)
    return ToolResult(
        call=call,
        ok=False,
        payload={
            "status": SKIPPED_STATUS,
            "error": f"Not run because the earlier planned step '{blocker.name}' failed.",
            "blocked_by": {"id": blocker.id, "tool": blocker.name},
            "arguments_sent": call.arguments,
        },
        egress=tool.egress if tool is not None else "metadata",
    )


def _project_changed_result(call: ToolCall) -> ToolResult:
    tool = get_tool_by_name(call.name)
    return ToolResult.failure(call, PROJECT_CHANGED_ERROR, tool.egress if tool is not None else "metadata")
