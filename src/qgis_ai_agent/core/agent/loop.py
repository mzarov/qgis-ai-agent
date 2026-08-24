from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.prompts import LOAD_SKILL_TOOL
from qgis_ai_agent.core.agent.request import build_step_request
from qgis_ai_agent.core.agent.transcript import ToolResult, Transcript
from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall
from qgis_ai_agent.core.llm.worker import ModelTurnThread
from qgis_ai_agent.qgis_tools.registry import (
    get_tool_by_name,
    summarize_tool_call,
    validate_tool_call,
)
from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "QGIS AI Agent"
MAX_ITERATIONS = 12
PRELOADED_SKILLS = ("inspect",)
THREAD_STOP_TIMEOUT_MS = 3000
LIMIT_REACHED_MESSAGE = (
    "Задача оказалась слишком длинной, я остановилась на достигнутом. "
    "Уточните запрос или разбейте его на части."
)


class AgentLoop(QObject):
    tool_started = pyqtSignal(str)
    tool_finished = pyqtSignal(str, bool)
    tool_queued = pyqtSignal(str)
    skill_loaded = pyqtSignal(str)
    confirm_needed = pyqtSignal(object, str)
    applied = pyqtSignal(object)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._executor = ToolExecutor()
        self._transcript = Transcript()
        self._history: list[dict[str, str]] = []
        self._loaded_skills: list[str] = []
        self._pending_writes: list[ToolCall] = []
        self._iteration = 0
        self._thread: ModelTurnThread | None = None
        self._prompt_protocol = "native"
        self._protocol_retried = False

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    @property
    def has_pending_writes(self) -> bool:
        return bool(self._pending_writes)

    def start(self, prompt: str, history: list[dict[str, str]] | None = None) -> None:
        self._transcript = Transcript()
        self._transcript.add_user(prompt)
        self._history = list(history or [])
        self._loaded_skills = [name for name in PRELOADED_SKILLS if SKILL_REGISTRY.get(name)]
        self._pending_writes = []
        self._iteration = 0
        self._protocol_retried = False
        self.busy_changed.emit(True)
        self._request_step()

    def stop(self) -> None:
        thread = self._thread
        self._thread = None
        if not thread or not thread.isRunning():
            return
        thread.requestInterruption()
        if thread.wait(THREAD_STOP_TIMEOUT_MS):
            return
        thread.terminate()
        thread.wait(THREAD_STOP_TIMEOUT_MS)

    def confirm_pending(self) -> None:
        calls = list(self._pending_writes)
        self._pending_writes = []
        if not calls:
            return
        self.busy_changed.emit(True)
        try:
            results = [self._apply(call) for call in calls]
        finally:
            self.busy_changed.emit(False)
        QgsMessageLog.logMessage(f"Применено изменений: {len(results)}.", LOG_TAG, Qgis.Info)
        self.applied.emit(results)

    def cancel_pending(self) -> None:
        self._pending_writes = []

    def _apply(self, call: ToolCall) -> ToolResult:
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
        QApplication.processEvents()
        result = self._executor.run(call)
        self.tool_finished.emit(call.name, result.ok)
        QApplication.processEvents()
        return result

    def _request_step(self) -> None:
        if self._iteration >= MAX_ITERATIONS:
            self._finish_on_limit()
            return
        self._iteration += 1
        try:
            request = build_step_request(self._transcript, self._loaded_skills, self._history)
        except Exception as err:
            self._fail(str(err))
            return
        self._prompt_protocol = request.protocol
        self._start_thread(request)

    def _start_thread(self, request) -> None:
        thread = ModelTurnThread(request.messages, request.tool_schemas, request.overrides)
        thread.finished_turn.connect(self._on_turn)
        thread.error.connect(self._on_error)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()

    def _on_turn(self, turn: ModelTurn) -> None:
        if self._needs_protocol_retry(turn):
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

    def _needs_protocol_retry(self, turn: ModelTurn) -> bool:
        return (
            turn.protocol == "json"
            and self._prompt_protocol == "native"
            and not self._protocol_retried
        )

    def _dispatch(self, call: ToolCall) -> ToolResult:
        if call.name == LOAD_SKILL_TOOL:
            return self._load_skill(call)

        tool = get_tool_by_name(call.name)
        if tool is not None and not tool.is_read_only:
            return self._queue_write(call)

        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
        result = self._executor.run(call)
        self.tool_finished.emit(call.name, result.ok)
        return result

    def _queue_write(self, call: ToolCall) -> ToolResult:
        try:
            validate_tool_call(call.name, dict(call.arguments))
        except Exception as err:
            self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
            self.tool_finished.emit(call.name, False)
            QgsMessageLog.logMessage(f"Шаг {call.name} отклонён: {err}", LOG_TAG, Qgis.Warning)
            return ToolResult(
                call=call,
                ok=False,
                payload={"error": str(err), "arguments_sent": call.arguments},
            )
        self._pending_writes.append(call)
        self.tool_queued.emit(summarize_tool_call(call.name, call.arguments))
        return ToolExecutor.queued(call)

    def _load_skill(self, call: ToolCall) -> ToolResult:
        name = str(call.arguments.get("name") or "").strip()
        skill = SKILL_REGISTRY.get(name)
        if not skill:
            return ToolResult(
                call=call,
                ok=False,
                payload={"error": f"Скилл не найден: {name}.", "available": SKILL_REGISTRY.names()},
            )
        if name not in self._loaded_skills:
            self._loaded_skills.append(name)
            self.skill_loaded.emit(name)
            QgsMessageLog.logMessage(f"Загружен скилл: {name}.", LOG_TAG, Qgis.Info)
        return ToolResult(call=call, ok=True, payload={"loaded": name, "tools": skill.tool_names})

    def _on_error(self, message: str) -> None:
        self._fail(message)

    def _complete(self, text: str) -> None:
        self._thread = None
        self.busy_changed.emit(False)
        if self._pending_writes:
            self.confirm_needed.emit(list(self._pending_writes), text)
        else:
            self.finished.emit(text)

    def _finish_on_limit(self) -> None:
        QgsMessageLog.logMessage(f"Достигнут лимит в {MAX_ITERATIONS} ходов.", LOG_TAG, Qgis.Warning)
        self._complete(LIMIT_REACHED_MESSAGE)

    def _fail(self, message: str) -> None:
        self._thread = None
        self._pending_writes = []
        self.busy_changed.emit(False)
        self.failed.emit(message)
