from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QObject, pyqtSignal

from qgis_ai_agent.core.agent.batch import WriteBatch
from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.notices import (
    APPLY_DECLINED_MESSAGE,
    APPLY_NOW_WITHOUT_WRITES,
    BUDGET_REACHED_MESSAGE,
    INTERJECTION_HEADER,
    LIMIT_REACHED_MESSAGE,
)
from qgis_ai_agent.core.agent.prompts import (
    APPLY_NOW_TOOL,
    LOAD_SKILL_TOOL,
    UPDATE_PLAN_TOOL,
    render_queued_steps,
    render_task_plan,
)
from qgis_ai_agent.core.agent.request import build_overrides, build_step_request
from qgis_ai_agent.core.agent.skills import load_skill
from qgis_ai_agent.core.agent.transcript import ToolResult, Transcript
from qgis_ai_agent.core.agent.turn_thread import TurnThreadOwner
from qgis_ai_agent.core.llm.transport import PROTOCOL_JSON, PROTOCOL_NATIVE, ModelTurn, ToolCall
from qgis_ai_agent.core.settings import get_token_budget
from qgis_ai_agent.qgis_tools.base import SAFETY_READ
from qgis_ai_agent.qgis_tools.project.snapshots import take_snapshot
from qgis_ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call
from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "QGIS AI Agent"
MAX_ITERATIONS = 40
PRELOADED_SKILLS = ("inspect",)


class AgentLoop(QObject):
    tool_started = pyqtSignal(str)
    tool_finished = pyqtSignal(str, bool)
    tool_queued = pyqtSignal(str)
    tool_rejected = pyqtSignal(str)
    skill_loaded = pyqtSignal(str)
    plan_changed = pyqtSignal(object, int)
    confirm_needed = pyqtSignal(object, str)
    usage_changed = pyqtSignal(int)
    answer_chunk = pyqtSignal(str)
    thinking_chunk = pyqtSignal(str)
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
        self._is_verification = False
        self._tokens_spent = 0
        self._token_budget = 0
        self._plan_steps: list[str] = []
        self._plan_done = 0
        self._staged = False
        self._pending_protocol = PROTOCOL_NATIVE
        self._verification_round = 0
        self._streamed_thinking = False

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    @property
    def has_pending_writes(self) -> bool:
        return bool(self._batch)

    def pending_writes(self) -> list[ToolCall]:
        return self._batch.pending()

    @property
    def is_verification(self) -> bool:
        return self._is_verification

    @property
    def verification_round(self) -> int:
        return self._verification_round

    def start(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        verification: bool = False,
        verification_round: int = 0,
    ) -> None:
        self._transcript = Transcript()
        self._transcript.add_user(prompt)
        self._history = list(history or [])
        self._is_verification = verification
        self._verification_round = verification_round
        self._tokens_spent = 0
        self._token_budget = get_token_budget()
        self._plan_steps = []
        self._plan_done = 0
        self._staged = False
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
        self._turn.detach(self._on_turn, self._fail, self._on_chunk, self._on_thinking)
        self._batch.clear()
        self.busy_changed.emit(False)
        self.aborted.emit()

    def stop(self) -> None:
        self._turn.stop()

    def interject(self, text: str) -> bool:
        message = (text or "").strip()
        if not message or not self.is_running:
            return False
        self._transcript.add_user(INTERJECTION_HEADER + message)
        QgsMessageLog.logMessage("The user interjected mid-run.", LOG_TAG, Qgis.Info)
        return True

    def confirm_pending(self) -> None:
        if not self._batch:
            return
        take_snapshot()
        self.busy_changed.emit(True)
        staged = self._staged
        self._staged = False
        try:
            results = self._batch.apply(self._on_apply_start, self._on_apply_finish)
        finally:
            if not staged:
                self.busy_changed.emit(False)
        QgsMessageLog.logMessage(f"Applied changes: {len(results)}.", LOG_TAG, Qgis.Info)
        if staged:
            self._resume_after_stage(results)
            return
        self.applied.emit(results)

    def cancel_pending(self) -> None:
        staged = self._staged
        self._staged = False
        self._batch.clear()
        if staged:
            self._complete(APPLY_DECLINED_MESSAGE)

    def _resume_after_stage(self, results: list[ToolResult]) -> None:
        self._transcript.add_results(results, self._pending_protocol)
        QgsMessageLog.logMessage("Stage applied, the run continues.", LOG_TAG, Qgis.Info)
        self._request_step()

    def _on_apply_start(self, call: ToolCall) -> None:
        self.tool_started.emit(summarize_tool_call(call.name, call.arguments))

    def _on_apply_finish(self, call: ToolCall, result: ToolResult) -> None:
        self.tool_finished.emit(call.name, result.ok)

    @property
    def tokens_spent(self) -> int:
        return self._tokens_spent

    def _request_step(self) -> None:
        if self._iteration >= MAX_ITERATIONS:
            self._finish_on_limit()
            return
        if self._token_budget and self._tokens_spent >= self._token_budget:
            self._finish_on_budget()
            return
        self._iteration += 1
        self._streamed_thinking = False
        try:
            request = build_step_request(
                self._transcript,
                self._loaded_skills,
                self._history,
                self._overrides,
                render_task_plan(self._plan_steps, self._plan_done),
                self._queued_summaries(),
            )
        except Exception as err:
            self._fail(str(err))
            return
        self._prompt_protocol = request.protocol
        self._pending_protocol = request.protocol
        self._turn.start(
            request.messages,
            request.tool_schemas,
            request.overrides,
            self._on_turn,
            self._fail,
            self._on_chunk,
            self._on_thinking,
        )

    def _queued_summaries(self) -> str:
        return render_queued_steps([summarize_tool_call(call.name, call.arguments) for call in self._batch.pending()])

    def _on_chunk(self, text: str) -> None:
        if not self._aborted and text:
            self.answer_chunk.emit(text)

    def _on_thinking(self, text: str) -> None:
        if self._aborted or not text:
            return
        self._streamed_thinking = True
        self.thinking_chunk.emit(text)

    def _replay_thinking(self, turn: ModelTurn) -> None:
        if turn.thinking and not self._streamed_thinking:
            self.thinking_chunk.emit(turn.thinking)

    def _on_turn(self, turn: ModelTurn) -> None:
        if self._aborted:
            return
        if turn.protocol == PROTOCOL_JSON and self._prompt_protocol == PROTOCOL_NATIVE and not self._protocol_retried:
            self._protocol_retried = True
            self._iteration -= 1
            self._request_step()
            return

        self._replay_thinking(turn)
        self._track_usage(turn)
        self._transcript.add_turn(turn)
        if not turn.tool_calls:
            self._complete(turn.text)
            return

        results = [self._dispatch(call) for call in turn.tool_calls]
        self._transcript.add_results(results, turn.protocol)
        if self._staged:
            self._pause_for_stage(turn.text)
            return
        self._request_step()

    def _pause_for_stage(self, text: str) -> None:
        self._turn.release()
        self.busy_changed.emit(False)
        self.confirm_needed.emit(self._batch.pending(), text)

    def _dispatch(self, call: ToolCall) -> ToolResult:
        if call.name == LOAD_SKILL_TOOL:
            return self._load_skill(call)
        if call.name == UPDATE_PLAN_TOOL:
            return self._update_plan(call)
        if call.name == APPLY_NOW_TOOL:
            return self._request_stage(call)

        tool = get_tool_by_name(call.name)
        if tool is None or tool.safety == SAFETY_READ:
            return self._run_now(call)
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

    def _request_stage(self, call: ToolCall) -> ToolResult:
        if not self._batch:
            return ToolResult.failure(call, APPLY_NOW_WITHOUT_WRITES)
        self._staged = True
        return ToolResult(call=call, ok=True, payload={"status": "awaiting_user"})

    def _update_plan(self, call: ToolCall) -> ToolResult:
        raw_steps = call.arguments.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult.failure(call, "steps must be a non-empty list of short strings.")
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
        try:
            done = max(0, min(len(steps), int(call.arguments.get("done") or 0)))
        except (TypeError, ValueError):
            done = 0
        self._plan_steps = steps
        self._plan_done = done
        self.plan_changed.emit(list(steps), done)
        return ToolResult(call=call, ok=True, payload={"steps": len(steps), "done": done})

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

    def _track_usage(self, turn: ModelTurn) -> None:
        spent = int(turn.input_tokens) + int(turn.output_tokens)
        if spent <= 0:
            return
        self._tokens_spent += spent
        self.usage_changed.emit(self._tokens_spent)

    def _finish_on_limit(self) -> None:
        QgsMessageLog.logMessage(f"Reached the limit of {MAX_ITERATIONS} turns.", LOG_TAG, Qgis.Warning)
        self._complete(LIMIT_REACHED_MESSAGE)

    def _finish_on_budget(self) -> None:
        QgsMessageLog.logMessage(
            f"Token budget hit: {self._tokens_spent} of {self._token_budget}.", LOG_TAG, Qgis.Warning
        )
        self._complete(BUDGET_REACHED_MESSAGE)

    def _fail(self, message: str) -> None:
        if self._aborted:
            return
        self._turn.release()
        self._batch.clear()
        self.busy_changed.emit(False)
        self.failed.emit(message)
