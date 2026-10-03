from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent import notices
from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.batch_apply import BatchApplyMixin
from ai_agent.core.agent.budget import TokenBudget
from ai_agent.core.agent.dispatch import DispatchMixin
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.prompts import render_queued_steps, render_task_plan
from ai_agent.core.agent.request import build_overrides, build_step_request
from ai_agent.core.agent.run_journal import RunJournal
from ai_agent.core.agent.skills import extend_loaded
from ai_agent.core.agent.transcript import ToolResult, Transcript
from ai_agent.core.agent.turn_thread import TurnThreadOwner
from ai_agent.core.llm.transport import PROTOCOL_JSON, PROTOCOL_NATIVE, ModelTurn, ToolCall
from ai_agent.core.settings import get_token_budget
from ai_agent.qgis_tools.web.http import cancel_active_requests
from ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "AI Agent"
MAX_ITERATIONS = 40
PRELOADED_SKILLS = ("inspect",)


class AgentLoop(BatchApplyMixin, DispatchMixin, QObject):
    # A CallSummary travels as an object: a str signal would hand the slot a plain copy without its marks.
    tool_started = pyqtSignal(object)
    tool_finished = pyqtSignal(str, bool)
    tool_queued = pyqtSignal(str)
    tool_rejected = pyqtSignal(object)
    skill_loaded = pyqtSignal(str)
    plan_changed = pyqtSignal(object, int)
    confirm_needed = pyqtSignal(object, str)
    question_asked = pyqtSignal(str)
    preamble = pyqtSignal(str)
    usage_changed = pyqtSignal(int)
    answer_chunk = pyqtSignal(str)
    thinking_chunk = pyqtSignal(str)
    applied = pyqtSignal(object)
    stage_applied = pyqtSignal(object)
    apply_interrupted = pyqtSignal(object)
    journal_written = pyqtSignal(str)
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
        self._invoked_skills: list[str] = []
        self._batch = WriteBatch(self._executor)
        self._iteration = 0
        self._turn = TurnThreadOwner()
        self._prompt_protocol = PROTOCOL_NATIVE
        self._overrides: dict = {}
        self._protocol_retried = False
        self._nudged = False
        self._aborted = False
        self._is_verification = False
        self._budget = TokenBudget()
        self._plan_steps: list[str] = []
        self._plan_done = 0
        self._staged = False
        self._pending_protocol = PROTOCOL_NATIVE
        self._verification_round = 0
        self._streamed_thinking = False
        self._question = ""
        self._stage_call: ToolCall | None = None
        self._generation = 0
        self._turn_callbacks: tuple | None = None
        self._active_apply_call: ToolCall | None = None
        self._journal = RunJournal()

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    @property
    def endpoint(self) -> str:
        return str(self._overrides.get("url_override") or "")

    @property
    def is_awaiting_answer(self) -> bool:
        return bool(self._question)

    @property
    def is_verification(self) -> bool:
        return self._is_verification

    @property
    def loaded_skills(self) -> list[str]:
        """Skills of the last run; they stay readable after it ends.

        The verification run starts with the same set: it re-reads what this
        run changed without a load_skill turn, and an identical tool list and
        system prompt let a caching provider reuse the prefix it just stored.
        """
        return list(self._loaded_skills)

    @property
    def verification_round(self) -> int:
        return self._verification_round

    def start(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        verification: bool = False,
        verification_round: int = 0,
        skills: list[str] | None = None,
        preload: list[str] | None = None,
        images: list[str] | None = None,
    ) -> bool:
        if self.is_running or self._batch.is_applying:
            return False
        self._generation += 1
        self._transcript = Transcript()
        self._transcript.add_user(prompt, images)
        self._journal.begin(prompt)
        self._history = list(history or [])
        self._is_verification = verification
        self._verification_round = verification_round
        self._budget.reset(get_token_budget())
        self._plan_steps = []
        self._plan_done = 0
        self._staged = False
        self._question = ""
        self._stage_call = None
        self._loaded_skills = [name for name in PRELOADED_SKILLS if SKILL_REGISTRY.get(name)]
        self._invoked_skills = [name for name in (skills or []) if SKILL_REGISTRY.get(name)]
        for name in [*(preload or []), *self._invoked_skills]:
            if SKILL_REGISTRY.get(name):
                extend_loaded(self._loaded_skills, name)
        self._batch.clear()
        self._iteration = 0
        self._protocol_retried = False
        self._nudged = False
        self._aborted = False
        self._overrides = build_overrides()
        self.busy_changed.emit(True)
        self._request_step()
        return True

    def abort(self) -> None:
        was_active = self.is_running or bool(self._batch) or bool(self._question)
        applying = self._batch.is_applying
        self._generation += 1
        self._question = ""
        self._stage_call = None
        self._aborted = True
        cancel_active_requests()
        if self._turn_callbacks is not None:
            self._turn.detach(*self._turn_callbacks)
            self._turn_callbacks = None
        else:
            self._turn.stop()
        self._batch.clear()
        if not applying:
            self._write_journal("Run stopped; completed changes remain.")
        self.busy_changed.emit(False)
        if was_active:
            self.aborted.emit()

    def stop(self) -> None:
        self._turn_callbacks = None
        self.abort()
        self._turn.stop()

    def interject(self, text: str) -> bool:
        message = (text or "").strip()
        if not message or not self.is_running:
            return False
        self._transcript.add_user(notices.INTERJECTION_HEADER + message)
        QgsMessageLog.logMessage("The user interjected mid-run.", LOG_TAG, Qgis.MessageLevel.Info)
        return True

    def answer(self, text: str) -> bool:
        reply = (text or "").strip()
        if not reply or not self._question:
            return False
        generation = self._generation
        self._question = ""
        self._transcript.add_user(reply)
        self.busy_changed.emit(True)
        if self._is_current(generation):
            self._request_step()
        return True

    @property
    def tokens_spent(self) -> int:
        return self._budget.spent

    @property
    def usage(self) -> dict[str, int]:
        """Prompt tokens, completion tokens and answered requests of the current or last run."""
        return self._budget.snapshot()

    def _request_step(self) -> None:
        generation = self._generation
        if not self._is_current(generation) or self._batch.is_applying:
            return
        if self._iteration >= MAX_ITERATIONS:
            self._finish_on_limit(generation)
            return
        if self._budget.exhausted:
            self._finish_on_budget(generation)
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
                invoked_skills=self._invoked_skills,
            )
        except Exception as err:
            self._fail(str(err), generation)
            return
        if not self._is_current(generation):
            return
        self._prompt_protocol = request.protocol
        self._pending_protocol = request.protocol
        callbacks = (
            lambda turn, current=generation: self._on_turn(turn, current),
            lambda message, current=generation: self._fail(message, current),
            lambda text, current=generation: self._on_chunk(text, current),
            lambda text, current=generation: self._on_thinking(text, current),
        )
        self._turn_callbacks = callbacks
        self._turn.start(
            request.messages,
            request.tool_schemas,
            request.overrides,
            *callbacks,
        )

    def _queued_summaries(self) -> str:
        return render_queued_steps(self._batch.pending_lines())

    def _on_chunk(self, text: str, generation: int | None = None) -> None:
        if self._is_current(generation) and text:
            self.answer_chunk.emit(text)

    def _on_thinking(self, text: str, generation: int | None = None) -> None:
        if not self._is_current(generation) or not text:
            return
        self._streamed_thinking = True
        self.thinking_chunk.emit(text)

    def _replay_thinking(self, turn: ModelTurn) -> None:
        if turn.thinking and not self._streamed_thinking:
            self.thinking_chunk.emit(turn.thinking)

    def _on_turn(self, turn: ModelTurn, generation: int | None = None) -> None:
        generation = self._generation if generation is None else generation
        if not self._is_current(generation):
            return
        if turn.protocol == PROTOCOL_JSON and self._prompt_protocol == PROTOCOL_NATIVE and not self._protocol_retried:
            self._protocol_retried = True
            self._iteration -= 1
            # The discarded turn was still answered, and billed.
            self._track_usage(turn)
            if self._is_current(generation):
                self._request_step()
            return

        self._replay_thinking(turn)
        if not self._is_current(generation):
            return
        self._track_usage(turn)
        if not self._is_current(generation):
            return
        self._transcript.add_turn(turn)
        if not turn.tool_calls and self._nudge_once(turn, generation):
            return
        if turn.tool_calls and turn.finish_reason in notices.TRUNCATED_REASONS:
            self._transcript.add_results(
                [ToolResult.failure(call, notices.CALLS_CUT_OFF) for call in turn.tool_calls], turn.protocol
            )
            self._request_step()
            return
        if not turn.tool_calls:
            self._complete(turn.text, generation)
            return

        if turn.text.strip():
            self.preamble.emit(turn.text)
            if not self._is_current(generation):
                return
        results = []
        for call in turn.tool_calls:
            if not self._is_current(generation):
                return
            results.append(self._dispatch(call))
            if not self._is_current(generation):
                return
        self._transcript.add_results(results, turn.protocol)
        if self._question:
            self._pause_for_question(generation)
            return
        if self._staged:
            self._pause_for_stage("", generation)
            return
        if self._is_current(generation):
            self._request_step()

    def _nudge_once(self, turn: ModelTurn, generation: int) -> bool:
        """Give a cut-off or empty final reply one more turn instead of ending the run."""
        truncated = turn.finish_reason in notices.TRUNCATED_REASONS
        if self._nudged or not (truncated or not turn.text.strip()):
            return False
        self._nudged = True
        if turn.text.strip():
            self.preamble.emit(turn.text)
            if not self._is_current(generation):
                return True
        self._transcript.add_user(notices.CONTINUE_TRUNCATED if truncated else notices.EMPTY_REPLY)
        self._request_step()
        return True

    def _pause_for_question(self, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self._turn.release()
        self._turn_callbacks = None
        self.busy_changed.emit(False)
        if not self._is_current(generation):
            return
        self.question_asked.emit(self._question)

    def _pause_for_stage(self, text: str, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self._turn.release()
        self._turn_callbacks = None
        self.busy_changed.emit(False)
        if not self._is_current(generation):
            return
        self.confirm_needed.emit(self._batch.pending(), text)

    def _complete(self, text: str, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self._staged = False
        self._stage_call = None
        self._turn.release()
        self._turn_callbacks = None
        self.busy_changed.emit(False)
        if not self._is_current(generation):
            return
        if self._batch:
            self.confirm_needed.emit(self._batch.pending(), text)
        else:
            self._write_journal(text)
            self.finished.emit(text)

    def _write_journal(self, outcome: str) -> None:
        path = self._journal.write(self._transcript.entries, outcome)
        if path:
            self.journal_written.emit(path)

    def _track_usage(self, turn: ModelTurn) -> None:
        if self._budget.add(turn):
            self.usage_changed.emit(self._budget.spent)

    def _finish_on_limit(self, generation: int | None = None) -> None:
        QgsMessageLog.logMessage(f"Reached the limit of {MAX_ITERATIONS} turns.", LOG_TAG, Qgis.MessageLevel.Warning)
        self._complete(notices.LIMIT_REACHED_MESSAGE, generation)

    def _finish_on_budget(self, generation: int | None = None) -> None:
        QgsMessageLog.logMessage(
            f"Token budget hit: {self._budget.spent} of {self._budget.limit}.", LOG_TAG, Qgis.MessageLevel.Warning
        )
        self._complete(notices.BUDGET_REACHED_MESSAGE, generation)

    def _fail(self, message: str, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self._turn.release()
        self._turn_callbacks = None
        self._staged = False
        self._stage_call = None
        self.busy_changed.emit(False)
        if not self._is_current(generation):
            return
        self._write_journal(f"Run failed: {message}")
        self.failed.emit(message)
        if self._batch and self._is_current(generation):
            self.confirm_needed.emit(self._batch.pending(), "")

    def _is_current(self, generation: int | None) -> bool:
        return not self._aborted and (generation is None or generation == self._generation)
