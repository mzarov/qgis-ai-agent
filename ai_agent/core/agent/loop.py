from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.config import limits
from ai_agent.core.agent import notices
from ai_agent.core.agent.announcements import announces_a_step
from ai_agent.core.agent.auto_apply import applies_itself
from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.batch_apply import BatchApplyMixin
from ai_agent.core.agent.budget import TokenBudget
from ai_agent.core.agent.compaction import estimated_tokens
from ai_agent.core.agent.dispatch import DispatchMixin
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.prompts import render_queued_steps, render_task_plan
from ai_agent.core.agent.repeats import FailureMemory
from ai_agent.core.agent.request import build_overrides, build_step_request
from ai_agent.core.agent.run_journal import RunJournal
from ai_agent.core.agent.skills import extend_loaded
from ai_agent.core.agent.transcript import ToolResult, Transcript
from ai_agent.core.agent.turn_thread import TurnCallbacks, TurnThreadOwner
from ai_agent.core.llm.failure_kinds import OTHER
from ai_agent.core.llm.retry import RetryNotice
from ai_agent.core.llm.turns import PROTOCOL_JSON, PROTOCOL_NATIVE, ModelTurn, ToolCall
from ai_agent.core.settings import get_token_budget
from ai_agent.qgis_tools.web.http import cancel_active_requests
from ai_agent.skills.registry import SKILL_REGISTRY

LOG_TAG = "AI Agent"
PRELOADED_SKILLS = ("inspect",)


class AgentLoop(BatchApplyMixin, DispatchMixin, QObject):  # type: ignore[misc]
    # object, not str: a str signal hands the slot a plain copy without the CallSummary's marks.
    tool_started = pyqtSignal(object)
    tool_finished = pyqtSignal(str, bool, str)
    tool_progressed = pyqtSignal(float, int)
    tool_queued = pyqtSignal(str)
    tool_rejected = pyqtSignal(object)
    skill_loaded = pyqtSignal(str)
    visual_ready = pyqtSignal(object)
    plan_changed = pyqtSignal(object, int)
    confirm_needed = pyqtSignal(object, str, bool)
    question_asked = pyqtSignal(str)
    preamble = pyqtSignal(str)
    turn_counted = pyqtSignal(int, int, bool)
    answer_chunk = pyqtSignal(str)
    thinking_chunk = pyqtSignal(str)
    retrying = pyqtSignal(object)
    applied = pyqtSignal(object)
    stage_applied = pyqtSignal(object)
    apply_interrupted = pyqtSignal(object)
    journal_written = pyqtSignal(str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    aborted = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._executor = ToolExecutor()
        self._transcript = Transcript()
        self._history: list[dict[str, str]] = []
        self._loaded_skills: list[str] = []
        self._invoked_skills: list[str] = []
        self._batch = WriteBatch(self._executor)
        self._iteration = 0
        self._max_steps = limits.DEFAULT_STEPS
        self._turn = TurnThreadOwner()
        self._prompt_protocol = PROTOCOL_NATIVE
        self._overrides: dict[str, Any] = {}
        self._protocol_retried = False
        self._nudged = False
        self._tools_called = False
        self._aborted = False
        self._is_verification = False
        self._budget = TokenBudget()
        self._request_estimate = 0
        self._planning = False
        self.ended_on_limit = False
        self._plan_steps: list[str] = []
        self._plan_done = 0
        self._staged = False
        self._pending_protocol = PROTOCOL_NATIVE
        self.failure_kind = ""
        self._verification_round = 0
        self._streamed_thinking = False
        self._question = ""
        self._question_options: list[str] = []
        self._stage_call: ToolCall | None = None
        self._declined: list[ToolCall] = []
        self._declined_project = ""
        self._generation = 0
        self._turn_callbacks: TurnCallbacks | None = None
        self._active_apply_call: ToolCall | None = None
        self._journal = RunJournal()
        self._failures = FailureMemory()

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    @property
    def endpoint(self) -> str:
        return str(self._overrides.get("url_override") or "")

    @property
    def overrides(self) -> dict[str, Any]:
        return dict(self._overrides)

    @property
    def is_awaiting_answer(self) -> bool:
        return bool(self._question)

    @property
    def question_options(self) -> list[str]:
        return list(self._question_options) if self._question else []

    @property
    def is_planning(self) -> bool:
        return self._planning

    @property
    def is_verification(self) -> bool:
        return self._is_verification

    @property
    def loaded_skills(self) -> list[str]:
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
        planning: bool = False,
    ) -> bool:
        if self.is_running or self._batch.is_applying:
            return False
        self._generation += 1
        self._transcript = Transcript()
        self._transcript.add_user(prompt, images)
        self._planning = planning
        self.ended_on_limit = False
        self._journal.begin(prompt)
        self._failures.reset()
        self._history = list(history or [])
        self._is_verification = verification
        self._verification_round = verification_round
        self._budget.reset(get_token_budget())
        self._max_steps = limits.max_steps()
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
        self._declined = []
        self._iteration = 0
        self._protocol_retried = False
        self._nudged = False
        self._tools_called = False
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
        self._declined = []
        if not applying:
            self._write_journal("Run stopped; completed changes remain.")
        self.busy_changed.emit(False)
        if was_active:
            self.aborted.emit()

    def stop(self) -> None:
        self._turn_callbacks = None
        self.abort()
        self._turn.stop()

    def shutdown(self) -> None:
        self.stop()
        # A step still working off the main thread must report to nobody once the plugin unloads.
        self._batch.detach()

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
    def usage(self) -> dict[str, int]:
        return self._budget.snapshot()

    def _request_step(self) -> None:
        generation = self._generation
        if not self._is_current(generation) or self._batch.is_applying:
            return
        if self._iteration >= self._max_steps:
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
                planning=self._planning,
            )
        except Exception as err:
            self._fail(str(err), generation)
            return
        if not self._is_current(generation):
            return
        self._prompt_protocol = request.protocol
        self._pending_protocol = request.protocol
        self._request_estimate = estimated_tokens(request.messages)
        callbacks = (
            lambda turn, current=generation: self._on_turn(turn, current),
            lambda message, current=generation: self._fail(message, current),
            lambda text, current=generation: self._on_chunk(text, current),
            lambda text, current=generation: self._on_thinking(text, current),
            lambda notice, current=generation: self._on_retry(notice, current),
        )
        self._turn_callbacks = callbacks
        self._journal.asked()
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

    def _on_retry(self, notice: RetryNotice, generation: int | None = None) -> None:
        if self._is_current(generation):
            self.retrying.emit(notice)

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
        if turn.tool_calls:
            self._tools_called = True
        elif self._nudge_once(turn, generation):
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
            results.append(self._failures.note(self._dispatch(call)))
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
        truncated = turn.finish_reason in notices.TRUNCATED_REASONS
        text = turn.text.strip()
        announced = not self._tools_called and announces_a_step(text)
        if self._nudged or not (truncated or not text or announced):
            return False
        self._nudged = True
        # A JSON-protocol reply is one object: its cut-off text is no answer, and a continued tail would not parse.
        resend = truncated and turn.protocol == PROTOCOL_JSON
        if text and not resend:
            self.preamble.emit(turn.text)
            if not self._is_current(generation):
                return True
        if resend:
            note = notices.CALLS_CUT_OFF
        elif truncated:
            note = notices.CONTINUE_TRUNCATED
        else:
            note = notices.ANNOUNCED_STEP if text else notices.EMPTY_REPLY
        self._transcript.add_user(note)
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
        self._offer(text)

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
            self._offer(text)
        else:
            self._write_journal(text)
            self.finished.emit(text)

    def _write_journal(self, outcome: str) -> None:
        path = self._journal.write(self._transcript.entries, outcome)
        if path:
            self.journal_written.emit(path)

    def _track_usage(self, turn: ModelTurn) -> None:
        self._budget.add(turn)
        prompt = max(0, int(turn.input_tokens)) or self._request_estimate
        self._journal.answered(prompt, max(0, int(turn.output_tokens)))
        self.turn_counted.emit(prompt, max(0, int(turn.output_tokens)), self._budget.requests == 1)

    def _finish_on_limit(self, generation: int | None = None) -> None:
        self.ended_on_limit = True
        QgsMessageLog.logMessage(f"Reached the limit of {self._max_steps} turns.", LOG_TAG, Qgis.MessageLevel.Warning)
        self._complete(notices.LIMIT_REACHED_MESSAGE, generation)

    def _finish_on_budget(self, generation: int | None = None) -> None:
        self.ended_on_limit = True
        QgsMessageLog.logMessage(
            f"Token budget hit: {self._budget.spent} of {self._budget.limit}.", LOG_TAG, Qgis.MessageLevel.Warning
        )
        self._complete(notices.BUDGET_REACHED_MESSAGE, generation)

    def _fail(self, message: str, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self.failure_kind = str(getattr(message, "kind", "") or OTHER)
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
            # Never auto-applied after a failure: the user looks first.
            self.confirm_needed.emit(self._batch.pending(), "", False)

    def _offer(self, text: str) -> None:
        calls = self._batch.pending()
        self.confirm_needed.emit(calls, text, applies_itself(calls))

    def _is_current(self, generation: int | None) -> bool:
        return not self._aborted and (generation is None or generation == self._generation)
