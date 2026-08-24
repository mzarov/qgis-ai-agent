from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.prompts import LOAD_SKILL_TOOL
from qgis_ai_agent.core.agent.request import build_step_request
from qgis_ai_agent.core.agent.transcript import ToolResult, Transcript
from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall
from qgis_ai_agent.core.llm.worker import ModelTurnThread
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call
from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "QGIS AI Agent"
# Страховка от зацикливания: столько ходов модели максимум на одну задачу.
MAX_ITERATIONS = 12
# Скилл чтения проекта загружен всегда — иначе простой вопрос стоит лишнего хода.
PRELOADED_SKILLS = ("inspect",)


class AgentLoop(QObject):
    """
    Агентный цикл: машина состояний в главном потоке.
    Сетевые вызовы уходят в ModelTurnThread, а исполнение тулов остаётся
    в главном потоке, где PyQGIS-объекты трогать безопасно.
    """

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
        """Идёт ли сейчас сетевой запрос."""
        return bool(self._thread and self._thread.isRunning())

    @property
    def has_pending_writes(self) -> bool:
        """Есть ли изменения, ожидающие подтверждения."""
        return bool(self._pending_writes)

    def start(self, prompt: str, history: list[dict[str, str]] | None = None) -> None:
        """Запускает новый прогон агента по запросу пользователя."""
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
        """Останавливает активный сетевой запрос — вызывается при выгрузке плагина."""
        thread = self._thread
        self._thread = None
        if thread and thread.isRunning():
            thread.terminate()
            thread.wait(2000)

    def confirm_pending(self) -> None:
        """Выполняет накопленный батч изменений после подтверждения пользователем."""
        calls = list(self._pending_writes)
        self._pending_writes = []
        if not calls:
            return
        results: list[ToolResult] = []
        for call in calls:
            self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
            result = self._executor.run(call)
            self.tool_finished.emit(call.name, result.ok)
            results.append(result)
        QgsMessageLog.logMessage(f"Применено изменений: {len(results)}.", LOG_TAG, Qgis.Info)
        self.applied.emit(results)

    def cancel_pending(self) -> None:
        """Отменяет накопленный батч без применения."""
        self._pending_writes = []

    def _request_step(self) -> None:
        """Отправляет следующий ход модели в фоновый поток."""
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

        thread = ModelTurnThread(request.messages, request.tool_schemas, request.overrides)
        thread.finished_turn.connect(self._on_turn)
        thread.error.connect(self._on_error)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()

    def _on_turn(self, turn: ModelTurn) -> None:
        """Слот главного потока: разбирает ход модели и решает, что делать дальше."""
        # Транспорт ушёл в фолбэк, а промпт был собран под нативный протокол —
        # пересобираем запрос один раз, чтобы модель получила формат ответа.
        if turn.protocol == "json" and self._prompt_protocol == "native" and not self._protocol_retried:
            self._protocol_retried = True
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
        """Направляет вызов: загрузка скилла, немедленное чтение или очередь на запись."""
        if call.name == LOAD_SKILL_TOOL:
            return self._load_skill(call)

        tool = get_tool_by_name(call.name)
        if tool is not None and not tool.is_read_only:
            self._pending_writes.append(call)
            self.tool_queued.emit(summarize_tool_call(call.name, call.arguments))
            return ToolExecutor.queued(call)

        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))
        result = self._executor.run(call)
        self.tool_finished.emit(call.name, result.ok)
        return result

    def _load_skill(self, call: ToolCall) -> ToolResult:
        """Обрабатывает мета-вызов загрузки скилла."""
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
        """Слот ошибки сетевого потока."""
        self._fail(message)

    def _complete(self, text: str) -> None:
        """Завершает прогон: либо финальный ответ, либо запрос подтверждения."""
        self._thread = None
        self.busy_changed.emit(False)
        if self._pending_writes:
            self.confirm_needed.emit(list(self._pending_writes), text)
        else:
            self.finished.emit(text)

    def _finish_on_limit(self) -> None:
        """Прогон упёрся в лимит ходов — отдаём то, что успели накопить."""
        QgsMessageLog.logMessage(f"Достигнут лимит в {MAX_ITERATIONS} ходов.", LOG_TAG, Qgis.Warning)
        self._complete(
            "Задача оказалась слишком длинной, я остановилась на достигнутом. "
            "Уточните запрос или разбейте его на части."
        )

    def _fail(self, message: str) -> None:
        """Аварийное завершение прогона."""
        self._thread = None
        self._pending_writes = []
        self.busy_changed.emit(False)
        self.failed.emit(message)
