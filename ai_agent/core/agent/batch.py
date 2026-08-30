import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QApplication

from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.common.layers import (
    layer_pin_error,
    pin_layer_references,
    validate_public_layer_references,
)
from ai_agent.qgis_tools.common.project_identity import project_identity
from ai_agent.qgis_tools.registry import get_tool_by_name, prepare_tool_call, summarize_tool_call

SKIPPED_STATUS = "skipped"
UNDO_TOOL = "undo_last_apply"
PROJECT_CHANGED_ERROR = (
    "The QGIS project changed while this plan was being applied. This step and every later step were stopped."
)
CANCELLED_ERROR = "The run was stopped. This pending step and every later step were cancelled."


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
        self._executing_call: ToolCall | None = None

    def __bool__(self) -> bool:
        return bool(self._calls) or self._applying

    @property
    def is_applying(self) -> bool:
        return self._applying

    @property
    def executing_tool(self) -> str:
        return self._executing_call.name if self._executing_call is not None else ""

    def clear(self) -> None:
        self._calls = []
        self._cancel_requested = self._applying

    def add(self, call: ToolCall) -> ToolCall:
        if self._applying:
            raise ValueError("Wait for the current plan to finish before adding another change.")
        public_arguments = validate_public_layer_references(call.arguments)
        prepared = pin_layer_references(prepare_tool_call(call.name, public_arguments))
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

    def pending_summaries(self) -> list[str]:
        return [summarize_tool_call(call.name, call.arguments) for call in self._calls]

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
                QApplication.processEvents()
                if failed is not None:
                    result = _skipped_result(call, failed.call)
                elif self._cancel_requested:
                    result = _cancelled_result(call)
                elif project_identity(QgsProject.instance()) != expected:
                    result = _project_changed_result(call)
                elif target_error := layer_pin_error(call.arguments):
                    result = _layer_changed_result(call, target_error)
                else:
                    self._executing_call = call
                    try:
                        result = self._executor.run(call)
                    finally:
                        self._executing_call = None
                on_finish(call, result)
                results.append(result)
                if not result.ok and failed is None:
                    failed = result
            return results
        finally:
            self._executing_call = None
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


def _cancelled_result(call: ToolCall) -> ToolResult:
    tool = get_tool_by_name(call.name)
    return ToolResult.failure(call, CANCELLED_ERROR, tool.egress if tool is not None else "metadata")


def _layer_changed_result(call: ToolCall, message: str) -> ToolResult:
    tool = get_tool_by_name(call.name)
    return ToolResult.failure(call, message, tool.egress if tool is not None else "metadata")
