import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from qgis.core import QgsProject

from ai_agent.core.agent.apply_run import ApplyRun
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.common.layers import pin_layer_references, validate_public_layer_references
from ai_agent.qgis_tools.common.project_identity import project_identity
from ai_agent.qgis_tools.registry import prepare_tool_call

UNDO_TOOL = "undo_last_apply"


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
        self._run: ApplyRun | None = None

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
        if self._applying and self._run is not None:
            self._run.cancel()

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

    def restore(self, calls: list[ToolCall]) -> None:
        if self._applying:
            raise ValueError("Wait for the current plan to finish before adding another change.")
        self._calls = list(calls)

    def _same_call(self, queued: ToolCall) -> ToolCall | None:
        signature = _signature(queued)
        for call in self._calls:
            if _signature(call) == signature:
                return call
        return None

    def pending(self) -> list[ToolCall]:
        return list(self._calls)

    def pending_lines(self) -> list[str]:
        return [_model_line(call) for call in self._calls]

    def apply(
        self,
        on_start: Callable[[ToolCall], Any],
        on_finish: Callable[[ToolCall, ToolResult], Any],
        expected_project_identity: str | None = None,
        done: Callable[[list[ToolResult]], Any] | None = None,
        on_progress: Callable[[float, int], Any] | None = None,
    ) -> list[ToolResult] | None:
        if self._applying:
            raise RuntimeError("This plan is already being applied.")
        calls = self._calls
        self._calls = []
        expected = expected_project_identity or project_identity(QgsProject.instance())
        self._applying = True
        self._cancel_requested = False
        ended: list[list[ToolResult]] = []

        def complete(results: list[ToolResult]) -> None:
            ended.append(results)
            if done is not None:
                done(results)

        self._run = ApplyRun(self, calls, on_start, on_finish, complete, expected, on_progress)
        self._run.advance()
        return ended[0] if ended else None

    def detach(self) -> None:
        if self._run is not None:
            self._run.detach()
        self._calls = []
        self._stop_applying()
        self._cancel_requested = True

    def _stop_applying(self) -> None:
        self._executing_call = None
        self._applying = False
        self._cancel_requested = False
        self._run = None


MODEL_LINE_LIMIT = 240


def _model_line(call: ToolCall) -> str:
    public = {key: value for key, value in call.arguments.items() if not str(key).startswith("_")}
    try:
        arguments = json.dumps(public, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        arguments = str(public)
    line = f"{call.name} {arguments}"
    return line if len(line) <= MODEL_LINE_LIMIT else line[: MODEL_LINE_LIMIT - 1] + "…"
