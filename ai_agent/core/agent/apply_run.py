from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.PyQt.QtWidgets import QApplication

from ai_agent.core.agent.transcript import SKIPPED_STATUS, ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.common.layers import follow_batch_renames, layer_names_by_id, layer_pin_error
from ai_agent.qgis_tools.common.project_identity import project_identity, same_project
from ai_agent.qgis_tools.registry import get_tool_by_name

if TYPE_CHECKING:
    from ai_agent.core.agent.batch import WriteBatch

LOG_TAG = "AI Agent"
PROJECT_CHANGED_ERROR = (
    "The QGIS project changed while this plan was being applied. This step and every later step were stopped."
)
CANCELLED_ERROR = "The run was stopped. This pending step and every later step were cancelled."
UNKNOWN = -1.0
SAVE_TOOL = "save_project"


class ApplyRun:
    def __init__(
        self,
        batch: "WriteBatch",
        calls: list[ToolCall],
        on_start: Callable[[ToolCall], Any],
        on_finish: Callable[[ToolCall, ToolResult], Any],
        done: Callable[[list[ToolResult]], Any],
        expected_project_identity: str,
        on_progress: Callable[[float, int], Any] | None = None,
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
        self._work: Any = None
        self._call: ToolCall | None = None
        self._percent = UNKNOWN
        self._done_count = 0
        self._detached = False

    def advance(self) -> None:
        try:
            while self._calls and not self._detached:
                call = self._calls.pop(0)
                self._on_start(call)
                QApplication.processEvents()
                if self._detached:
                    break
                result = self._blocked(call)
                if result is None:
                    self._batch._executing_call = call
                    work = self._batch._executor.start(call, self._ended)
                    if work is not None:
                        self._work, self._call = work, call
                        self._percent, self._done_count = UNKNOWN, 0
                        work.progressed.connect(self._progressed)
                        work.counted.connect(self._counted)
                        self._tell_progress()
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

    def _progressed(self, percent: float) -> None:
        self._percent = float(percent)
        self._tell_progress()

    def _counted(self, done: int) -> None:
        self._done_count = int(done)
        self._tell_progress()

    def _tell_progress(self) -> None:
        if self._on_progress is not None and not self._detached:
            self._on_progress(self._percent, self._done_count)

    def cancel(self) -> None:
        if self._work is not None:
            self._work.cancel()

    def detach(self) -> None:
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
            QgsMessageLog.logMessage(f"Applying stopped ({type(err).__name__}).", LOG_TAG, Qgis.MessageLevel.Warning)
            self._finish()
            return
        self.advance()

    def _blocked(self, call: ToolCall) -> ToolResult | None:
        if self._failed is not None:
            return _skipped_result(call, self._failed.call)
        if self._batch._cancel_requested:
            return _failure(call, CANCELLED_ERROR)
        if not same_project(project_identity(QgsProject.instance()), self._expected):
            return _failure(call, PROJECT_CHANGED_ERROR)
        target_error = layer_pin_error(_follow(call, self._names_at_start))
        return _failure(call, target_error) if target_error else None

    def _record(self, call: ToolCall, result: ToolResult) -> None:
        if result.ok and call.name == SAVE_TOOL:
            # Saved under a new name, the project is the same one: the steps after it still apply to it.
            self._expected = project_identity(QgsProject.instance())
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
    followed = follow_batch_renames(call.arguments, names_at_start)
    if followed is not call.arguments:
        call.arguments.clear()
        call.arguments.update(followed)
    return call.arguments
