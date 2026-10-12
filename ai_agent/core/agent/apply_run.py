"""Applying one batch, step by step; a step that works off the main thread is waited for, never blocked on.

Before every step the run checks what would make it wrong now: an earlier step
failed, the run was stopped, the project is another one, a pinned layer moved.
A step whose tool works long goes to the background (`ToolExecutor.start`): the
run returns to Qt's event loop and goes on when the step's result arrives, so
the window, the map and Stop stay alive. With no such step the whole batch is
applied before `WriteBatch.apply` returns, as it always was.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.PyQt.QtWidgets import QApplication

from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.common.layers import follow_batch_renames, layer_names_by_id, layer_pin_error
from ai_agent.qgis_tools.common.project_identity import project_identity
from ai_agent.qgis_tools.registry import get_tool_by_name

if TYPE_CHECKING:
    from ai_agent.core.agent.batch import WriteBatch

LOG_TAG = "AI Agent"
SKIPPED_STATUS = "skipped"
PROJECT_CHANGED_ERROR = (
    "The QGIS project changed while this plan was being applied. This step and every later step were stopped."
)
CANCELLED_ERROR = "The run was stopped. This pending step and every later step were cancelled."


class ApplyRun:
    """One batch being applied; `done` gets every step's result once the last one has ended."""

    def __init__(
        self,
        batch: "WriteBatch",
        calls: list[ToolCall],
        on_start: Callable[[ToolCall], Any],
        on_finish: Callable[[ToolCall, ToolResult], Any],
        done: Callable[[list[ToolResult]], Any],
        expected_project_identity: str,
        on_progress: Callable[[float], Any] | None = None,
    ) -> None:
        self._batch = batch
        self._calls = list(calls)
        self._on_start = on_start
        self._on_finish = on_finish
        self._done = done
        self._on_progress = on_progress
        self._expected = expected_project_identity
        self._names_at_start = layer_names_by_id()
        self._results: list[ToolResult] = []
        self._failed: ToolResult | None = None
        # The step working off the main thread, while it works.
        self._work: Any = None
        self._call: ToolCall | None = None
        self._detached = False

    def advance(self) -> None:
        """Apply steps until one goes to the background or none is left."""
        try:
            while self._calls and not self._detached:
                call = self._calls.pop(0)
                self._on_start(call)
                QApplication.processEvents()
                result = self._blocked(call)
                if result is None:
                    self._batch._executing_call = call
                    work = self._batch._executor.start(call, self._ended)
                    if work is not None:
                        self._work, self._call = work, call
                        if self._on_progress is not None:
                            work.progressed.connect(self._on_progress)
                        return
                    try:
                        result = self._batch._executor.run(call)
                    finally:
                        self._batch._executing_call = None
                self._record(call, result)
        except BaseException:
            self._batch._stop_applying()
            raise
        if not self._detached:
            self._finish()

    def cancel(self) -> None:
        """Stop the step working in the background; its result comes back as a failure, as usual."""
        if self._work is not None:
            self._work.cancel()

    def detach(self) -> None:
        """Stop and forget: whatever the background step reports later reaches nobody (plugin unload)."""
        self._detached = True
        self.cancel()

    def _ended(self, result: ToolResult) -> None:
        if self._detached:
            return
        call = self._call
        self._work, self._call = None, None
        self._batch._executing_call = None
        if call is None:
            return
        try:
            self._record(call, result)
        except Exception as err:
            # A hook failed after the step's work was done: end the run rather than leave it applying forever.
            QgsMessageLog.logMessage(f"Applying stopped ({type(err).__name__}).", LOG_TAG, Qgis.MessageLevel.Warning)
            self._finish()
            return
        self.advance()

    def _blocked(self, call: ToolCall) -> ToolResult | None:
        """The result of a step that must not run now, or None when it may."""
        if self._failed is not None:
            return _skipped_result(call, self._failed.call)
        if self._batch._cancel_requested:
            return _failure(call, CANCELLED_ERROR)
        if project_identity(QgsProject.instance()) != self._expected:
            return _failure(call, PROJECT_CHANGED_ERROR)
        target_error = layer_pin_error(_follow(call, self._names_at_start))
        return _failure(call, target_error) if target_error else None

    def _record(self, call: ToolCall, result: ToolResult) -> None:
        self._on_finish(call, result)
        self._results.append(result)
        if not result.ok and self._failed is None:
            self._failed = result

    def _finish(self) -> None:
        self._batch._stop_applying()
        self._done(self._results)


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


def _failure(call: ToolCall, message: str) -> ToolResult:
    tool = get_tool_by_name(call.name)
    return ToolResult.failure(call, message, tool.egress if tool is not None else "metadata")


def _follow(call: ToolCall, names_at_start: dict[str, str]) -> dict[str, Any]:
    """The call's arguments after renames earlier in this batch, updated in place: the call is tracked by identity."""
    followed = follow_batch_renames(call.arguments, names_at_start)
    if followed is not call.arguments:
        call.arguments.clear()
        call.arguments.update(followed)
    return call.arguments
