from qgis.core import Qgis, QgsMessageLog, QgsProject

from qgis_ai_agent.core.agent import notices
from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, effective_safety
from qgis_ai_agent.qgis_tools.common.project_identity import project_identity
from qgis_ai_agent.qgis_tools.project.snapshots import snapshot_error, take_snapshot
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call

LOG_TAG = "QGIS AI Agent"


class BatchApplyMixin:
    @property
    def has_pending_writes(self) -> bool:
        return bool(self._batch)

    @property
    def is_applying(self) -> bool:
        return self._batch.is_applying

    @property
    def active_apply_tool(self) -> str:
        return self._batch.executing_tool

    def pending_writes(self) -> list[ToolCall]:
        return self._batch.pending()

    def confirm_pending(self) -> None:
        if not self._batch or self._batch.is_applying:
            return
        generation = self._generation
        staged = self._staged
        self._staged = False
        calls = self._batch.pending()
        undo_only = len(calls) == 1 and calls[0].name == "undo_last_apply"
        expected_project_identity = project_identity(QgsProject.instance())
        snapshot_needed = any(_call_requires_snapshot(call) for call in calls)
        if snapshot_needed and not undo_only and not take_snapshot():
            self._snapshot_failed(calls, staged, generation)
            return
        self.busy_changed.emit(True)
        try:
            results = self._batch.apply(
                lambda call: self._on_apply_start(call, generation),
                lambda call, result: self._on_apply_finish(call, result, generation),
                expected_project_identity,
            )
        except Exception:
            if not staged and self._is_current(generation):
                self.busy_changed.emit(False)
            raise
        finally:
            self._active_apply_call = None
        if not self._is_current(generation):
            self.apply_interrupted.emit(results)
            return
        QgsMessageLog.logMessage(f"Applied changes: {len(results)}.", LOG_TAG, Qgis.Info)
        if staged:
            self.stage_applied.emit(results)
            if self._is_current(generation):
                self._resume_after_stage(results)
            return
        self.applied.emit(results)
        if self._is_current(generation):
            self.busy_changed.emit(False)

    def _snapshot_failed(self, calls: list[ToolCall], staged: bool, generation: int) -> None:
        self._batch.clear()
        if not self._is_current(generation):
            return
        message = snapshot_error() or notices.SNAPSHOT_FAILED_MESSAGE
        results = [ToolResult.failure(call, message, _call_egress(call)) for call in calls]
        QgsMessageLog.logMessage(message, LOG_TAG, Qgis.Critical)
        if staged:
            self.stage_applied.emit(results)
            if self._is_current(generation):
                self._resume_after_stage(results)
        else:
            self.applied.emit(results)

    def cancel_pending(self) -> None:
        if self._batch.is_applying:
            self.abort()
            return
        staged = self._staged
        had_pending = bool(self._batch) or staged
        self._staged = False
        self._stage_call = None
        self._batch.clear()
        if had_pending:
            self._generation += 1
        if staged:
            self._complete(notices.APPLY_DECLINED_MESSAGE)

    def _resume_after_stage(self, results: list[ToolResult]) -> None:
        generation = self._generation
        replacements = list(results)
        if self._stage_call is not None:
            status = "applied" if all(result.ok for result in results) else "failed"
            replacements.append(ToolResult(call=self._stage_call, payload={"status": status}))
        self._stage_call = None
        self._transcript.replace_results(replacements, self._pending_protocol)
        QgsMessageLog.logMessage("Stage applied, the run continues.", LOG_TAG, Qgis.Info)
        if self._is_current(generation):
            self._request_step()

    def _on_apply_start(self, call: ToolCall, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self._active_apply_call = call
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))

    def _on_apply_finish(
        self,
        call: ToolCall,
        result: ToolResult,
        generation: int | None = None,
    ) -> None:
        if not self._is_current(generation) and call is not self._active_apply_call:
            return
        self.tool_finished.emit(call.name, result.ok)
        if call is self._active_apply_call:
            self._active_apply_call = None


def _call_egress(call: ToolCall) -> str:
    tool = get_tool_by_name(call.name)
    return tool.egress if tool is not None else "metadata"


def _call_requires_snapshot(call: ToolCall) -> bool:
    tool = get_tool_by_name(call.name)
    return tool is None or effective_safety(tool, call.arguments) != SAFETY_READ
