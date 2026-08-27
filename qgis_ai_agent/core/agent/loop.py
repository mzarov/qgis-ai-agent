from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QObject, pyqtSignal

from qgis_ai_agent.core.agent.batch import WriteBatch
from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.notices import (
    DESTRUCTIVE_NOT_SUPPORTED,
    LIMIT_REACHED_MESSAGE,
)
from qgis_ai_agent.core.agent.prompts import LOAD_SKILL_TOOL
from qgis_ai_agent.core.agent.request import build_overrides, build_step_request
from qgis_ai_agent.core.agent.skills import load_skill
from qgis_ai_agent.core.agent.transcript import ToolResult, Transcript
from qgis_ai_agent.core.agent.turn_thread import TurnThreadOwner
from qgis_ai_agent.core.llm.transport import PROTOCOL_JSON, PROTOCOL_NATIVE, ModelTurn, ToolCall
from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_READ
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call
from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "QGIS AI Agent"
MAX_ITERATIONS = 12
PRELOADED_SKILLS = ("inspect",)


class AgentLoop(QObject):
    tool_started = pyqtSignal(str)
    tool_finished = pyqtSignal(str, bool)
    tool_queued = pyqtSignal(str)
    tool_rejected = pyqtSignal(str)
    skill_loaded = pyqtSignal(str)
    confirm_needed = pyqtSignal(object, str)
    applied = pyqtSignal(object)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    aborted = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._executor = ToolExecutor()
        self._transcript = Transcript()
        self._history: list[dict[str, str]] = []
        self._loaded_skills: list[str] = []
        self._batch = WriteBatch(self._executor)
        self._iteration = 0
        self._turn = TurnThreadOwner()
        self._prompt_protocol = PROTOCOL_NATIVE
        self._overrides: dict = {}
        self._protocol_retried = False
        self._aborted = False

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    @property
    def has_pending_writes(self) -> bool:
        return bool(self._batch)

    def start(self, prompt: str, history: list[dict[str, str]] | None = None) -> None:
        self._transcript = Transcript()
        self._transcript.add_user(prompt)
        self._history = list(history or [])
        self._loaded_skills = [name for name in PRELOADED_SKILLS if SKILL_REGISTRY.get(name)]
        self._batch.clear()
        self._iteration = 0
        self._protocol_retried = False
        self._aborted = False
        self._overrides = build_overrides()
        self.busy_changed.emit(True)
        self._request_step()

    def abort(self) -> None:
        if not self.is_running and not self._batch:
            return
        self._aborted = True
        self._turn.detach(self._on_turn, self._fail)
        self._batch.clear()
        self.busy_changed.emit(False)
        self.aborted.emit()

    def stop(self) -> None:
        self._turn.stop()

    def confirm_pending(self) -> None:
        if not self._batch:
            return
        self.busy_changed.emit(True)
        try:
            results = self._batch.apply(self._on_apply_start, self._on_apply_finish)
        finally:
            self.busy_changed.emit(False)
        QgsMessageLog.logMessage(f"Applied changes: {len(results)}.", LOG_TAG, Qgis.Info)
        self.applied.emit(results)

    def cancel_pending(self) -> None:
        self._batch.clear()

    def _on_apply_start(self, call: ToolCall) -> None:
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))

    def _on_apply_finish(self, call: ToolCall, result: ToolResult) -> None:
        self.tool_finished.emit(call.name, result.ok)

    def _request_step(self) -> None:
        if self._iteration >= MAX_ITERATIONS:
            self._finish_on_limit()
            return
        self._iteration += 1
        try:
            request = build_step_request(self._transcript, self._loaded_skills, self._history, self._overrides)
        except Exception as err:
            self._fail(str(err))
            return
        self._prompt_protocol = request.protocol
        self._turn.start(request.messages, request.tool_schemas, request.overrides, self._on_turn, self._fail)

    def _on_turn(self, turn: ModelTurn) -> None:
        if self._aborted:
            return
        if turn.protocol == PROTOCOL_JSON and self._prompt_protocol == PROTOCOL_NATIVE and not self._protocol_retried:
            self._protocol_retried = True
            self._iteration -= 1
            self._request_step()
            return

        self._transcript.add_turn(turn)
        if not turn.tool_calls:
            self._complete(turn.text)
            return

        results = [self._dispatch(call) for call in turn.tool_calls]
        self._transcript.add_results(results, turn.protocol)
        self._request_step()

    def _dispatch(self, call: ToolCall) -> ToolResult:
        if call.name == LOAD_SKILL_TOOL:
            return self._load_skill(call)

        tool = get_tool_by_name(call.name)
        if tool is None:
            return self._run_now(call)
        if tool.safety == SAFETY_READ:
            return self._run_now(call)
        if tool.safety == SAFETY_DESTRUCTIVE:
            return ToolResult.failure(call, DESTRUCTIVE_NOT_SUPPORTED)
        return self._queue_write(call)

    def _run_now(self, call: ToolCall) -> ToolResult:
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
        result = self._executor.run(call)
        self.tool_finished.emit(call.name, result.ok)
        return result

    def _queue_write(self, call: ToolCall) -> ToolResult:
        try:
            queued = self._batch.add(call)
        except Exception as err:
            self.tool_rejected.emit(summarize_tool_call(call.name, call.arguments))
            QgsMessageLog.logMessage(f"Step {call.name} rejected: {err}", LOG_TAG, Qgis.Warning)
            return ToolResult.failure(call, str(err))
        self.tool_queued.emit(summarize_tool_call(queued.name, queued.arguments))
        return ToolExecutor.queued(queued)

    def _load_skill(self, call: ToolCall) -> ToolResult:
        result, loaded = load_skill(call, self._loaded_skills)
        if loaded:
            self.skill_loaded.emit(loaded)
            QgsMessageLog.logMessage(f"Skill loaded: {loaded}.", LOG_TAG, Qgis.Info)
        return result

    def _complete(self, text: str) -> None:
        self._turn.release()
        self.busy_changed.emit(False)
        if self._batch:
            self.confirm_needed.emit(self._batch.pending(), text)
        else:
            self.finished.emit(text)

    def _finish_on_limit(self) -> None:
        QgsMessageLog.logMessage(f"Reached the limit of {MAX_ITERATIONS} turns.", LOG_TAG, Qgis.Warning)
        self._complete(LIMIT_REACHED_MESSAGE)

    def _fail(self, message: str) -> None:
        if self._aborted:
            return
        self._turn.release()
        self._batch.clear()
        self.busy_changed.emit(False)
        self.failed.emit(message)
