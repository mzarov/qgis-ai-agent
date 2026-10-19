from typing import Any

from qgis.core import Qgis

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.context.project import layer_choices
from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import safe_endpoint_label
from ai_agent.core.llm.retry import RetryNotice
from ai_agent.core.local_skills import register_local_skills
from ai_agent.core.orchestrator import attaching
from ai_agent.core.orchestrator.compacting import SessionCompaction
from ai_agent.core.orchestrator.contracts import DockWidgetContract, RetryArgs
from ai_agent.core.orchestrator.naming import SessionNaming
from ai_agent.core.orchestrator.notices import (
    DATA_SHARING_DECLINED,
    INTERJECTED,
    MESSAGE_DURATION_SEC,
    RUN_STOPPED,
    SWITCH_WHILE_RUNNING,
    UNKNOWN_SKILL,
)
from ai_agent.core.orchestrator.plans import PlanMixin
from ai_agent.core.orchestrator.presentation import active_layer_chip, is_configured, project_line
from ai_agent.core.orchestrator.project_lifecycle import ProjectLifecycleMixin
from ai_agent.core.orchestrator.rewind import Checkpoint, RewindMixin
from ai_agent.core.orchestrator.run_events import RunEventsMixin
from ai_agent.core.orchestrator.sessions import SessionsMixin
from ai_agent.core.orchestrator.slash import available_names, choices, is_known_skill, parse_slash, prompt_for
from ai_agent.core.settings import (
    get_api_url,
    get_data_sharing_consent,
    get_model,
    get_planning,
    get_work_mode,
    set_data_sharing_consent,
)
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.usage_stats import UsageStats
from ai_agent.i18n import tr


class CoreOrchestrator(SessionsMixin, PlanMixin, RunEventsMixin, ProjectLifecycleMixin, RewindMixin):
    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.conversation = ConversationState()
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
        self._plan_step = -1
        self._apply_scope: tuple[str, str] | None = None
        self._checkpoints: list[Checkpoint] = []
        self._plan_snapshots: dict[int, str] = {}
        self._plan_keys: dict[int, str] = {}
        self._plan_marks: list[list[str]] = []
        self._restorable_plan_id: int | None = None
        self._retry_args: RetryArgs | None = None
        self._done_summary = ""
        self._snapshot_before_apply = ""
        self._invalidated_scope: tuple[str, str] | None = None
        self._deferred_interrupted_outcome = ""
        self._last_request = ""
        self.compaction = SessionCompaction(self.dock_widget, lambda: self.conversation)
        self.naming = SessionNaming(lambda: self.conversation, self._show_title)
        self.usage = UsageStats()
        self._connect_agent()
        self.usage.flush()
        self.dock_widget.set_session_source(self.conversation.recent)
        self.refresh_configured()

    def refresh_configured(self) -> None:
        register_local_skills()
        self.conversation.prune_history()
        self.dock_widget.set_project_line(project_line())
        self.dock_widget.set_configured(_is_configured())
        self.dock_widget.set_model(get_model() if _is_configured() else "")
        self.dock_widget.set_work_mode(get_work_mode())
        self.dock_widget.set_skill_source(choices)
        self.dock_widget.set_layer_source(layer_choices)
        self.on_active_layer_changed()
        self.compaction.refresh()

    def _connect_agent(self) -> None:
        self.agent.tool_started.connect(self.on_tool_started)
        self.agent.tool_finished.connect(self.on_tool_finished)
        self.agent.tool_progressed.connect(self.on_tool_progressed)
        self.agent.tool_queued.connect(self.on_tool_queued)
        self.agent.tool_rejected.connect(self.on_tool_rejected)
        self.agent.skill_loaded.connect(self.on_skill_loaded)
        self.agent.visual_ready.connect(self.on_visual_ready)
        self.agent.plan_changed.connect(self.on_plan_changed)
        self.agent.confirm_needed.connect(self.on_confirm_needed)
        self.agent.question_asked.connect(self.on_question_asked)
        self.agent.preamble.connect(self.on_preamble)
        self.agent.applied.connect(self.on_applied)
        self.agent.stage_applied.connect(self.on_stage_applied)
        self.agent.apply_interrupted.connect(self.on_apply_interrupted)
        self.agent.journal_written.connect(self.on_journal_written)
        self.agent.finished.connect(self.on_finished)
        self.agent.failed.connect(self.on_failed)
        self.agent.aborted.connect(self.on_aborted)
        # Via the orchestrator, not the dock's methods: a rebuilt dock must receive these too.
        self.agent.busy_changed.connect(self.on_busy)
        self.agent.turn_counted.connect(self.on_turn_counted)
        self.agent.answer_chunk.connect(self.on_answer_chunk)
        self.agent.thinking_chunk.connect(self.on_thinking_chunk)
        self.agent.retrying.connect(self.on_retrying)

    def on_busy(self, busy: bool) -> None:
        self.dock_widget.set_busy(busy)
        if not busy:
            self.usage.flush()
            self.dock_widget.set_run_kind("")
            self.on_active_layer_changed()

    def on_active_layer_changed(self, *_layer: Any) -> None:
        name, detail = active_layer_chip(self.iface)
        self.dock_widget.set_active_layer(name, detail)

    def _show_title(self) -> None:
        self.dock_widget.set_conversation_title(self.conversation.title)

    def on_answer_chunk(self, text: str) -> None:
        self.dock_widget.add_stream_chunk(text)

    def on_thinking_chunk(self, text: str) -> None:
        self.dock_widget.add_thinking_chunk(text)
        self.conversation.trace.thinking(text)

    def on_retrying(self, notice: RetryNotice) -> None:
        self.dock_widget.show_retry(notice.seconds, notice.attempt, notice.total, notice.busy)

    def on_stop(self) -> None:
        if self.compaction.is_running:
            self.compaction.cancel()
            self.dock_widget.add_system_message(RUN_STOPPED)
            return
        self.agent.abort()

    def on_prompt(self, prompt: str) -> None:
        text = (prompt or "").strip()
        if not text:
            self._push_message(tr("Type a request."), Qgis.MessageLevel.Warning)
            return
        if bool(getattr(self.agent, "is_applying", False)):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if self.compaction.is_running:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if self.agent.is_running:
            self._interject(text)
            return
        if self.agent.is_awaiting_answer:
            self._answer(text)
            return
        mention = self.dock_widget.context_mention()
        if isinstance(mention, str) and mention and mention not in text:
            text = f"{text} {mention}"
        skill, rest = parse_slash(text)
        if skill and not is_known_skill(skill):
            self.dock_widget.add_system_message(UNKNOWN_SKILL.format(skill, available_names()))
            return
        if not self._confirm_first_send():
            return
        pictures = attaching.take_pictures(self.dock_widget)
        self.dock_widget.clear_prompt()
        self._start_run(
            attaching.with_names(text, pictures),
            prompt_for(skill, rest) if skill else text,
            text,
            skills=[skill] if skill else None,
            images=pictures.encoded,
        )

    def _start_run(
        self,
        shown: str,
        prompt: str,
        request: str,
        skills: list[str] | None = None,
        images: list[str] | None = None,
    ) -> None:
        self.dock_widget.begin_work()
        self.usage.note("runs")
        entry = self._show_user_bubble(shown)
        self._forget_restore()
        self._drop_pending_plan()
        # Dropping a staged plan ends its run with an answer, saved before this request: the place follows it.
        self.dock_widget.mark_rewind_point(entry, self.conversation.next_place)
        planning = get_planning()

        def begin() -> None:
            history = self.conversation.window()
            self.conversation.add("user", shown)
            self._show_title()
            self._last_request = request
            self._done_summary = ""
            self._retry_args = (shown, prompt, request, skills, images, planning)
            self.agent.start(prompt, history, skills=skills, images=images, planning=planning)

        def stopped() -> None:
            self.conversation.add("user", shown)

        if not (self.compaction.needed() and self.compaction.start(after=begin, cancelled=stopped)):
            begin()

    def on_retry(self) -> None:
        if not self.is_idle:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        if self._retry_args is None:
            return
        shown, prompt, request, skills, images, planning = self._retry_args
        self.dock_widget.clear_prompt()
        history = self.conversation.window()
        if history and history[-1].get("role") == "user" and history[-1].get("content") == shown:
            history = history[:-1]
        self._last_request = request
        self.dock_widget.drop_failures()
        self.conversation.drop_failures()
        self.dock_widget.begin_work()
        self.agent.start(prompt, history, skills=skills, images=images, planning=planning)

    def on_settings_saved(self) -> None:
        if self._retry_args is not None and self.is_idle:
            self.dock_widget.offer_retry()

    @property
    def is_idle(self) -> bool:
        return not (
            self.agent.is_running
            or bool(getattr(self.agent, "is_applying", False))
            or self.agent.has_pending_writes
            or self.agent.is_awaiting_answer
            or self.compaction.is_running
        )

    def attach_dock(self, dock_widget: DockWidgetContract) -> None:
        self.dock_widget = dock_widget
        self.compaction.attach(dock_widget)
        self.dock_widget.set_session_source(self.conversation.recent)
        self.refresh_configured()
        self._replay()

    def on_compact(self) -> None:
        if not self.is_idle:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        self.dock_widget.begin_work()
        self.compaction.start()

    def on_turn_counted(self, prompt_tokens: int, completion_tokens: int, opens_run: bool = True) -> None:
        self.conversation.count_turn(prompt_tokens, completion_tokens, measure=opens_run)
        self.compaction.refresh()

    def on_files_attached(self, paths: list[str]) -> None:
        attaching.files_attached(self.dock_widget, paths)

    def _confirm_first_send(self, endpoint: str | None = None) -> bool:
        if not _is_configured():
            return True
        url = (endpoint if endpoint is not None else get_api_url() or "").strip()
        if not url or is_local(url) or get_data_sharing_consent(url):
            return True
        if not self.dock_widget.confirm_data_sharing(safe_endpoint_label(url)):
            self.dock_widget.add_system_message(DATA_SHARING_DECLINED)
            return False
        set_data_sharing_consent(True, url)
        return True

    def _answer(self, text: str) -> None:
        if not self._confirm_first_send(getattr(self.agent, "endpoint", None)):
            return
        self._show_user_message(text)
        self.dock_widget.clear_prompt()
        chosen = text in list(getattr(self.agent, "question_options", None) or [])
        self.conversation.add("user", text, chosen=chosen)
        self.dock_widget.begin_work()
        self.agent.answer(text)

    def _interject(self, text: str) -> None:
        if not self.agent.interject(text):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        self._show_user_message(text)
        self.dock_widget.clear_prompt()
        self.dock_widget.add_system_message(INTERJECTED)
        self.conversation.add("user", text)

    def _show_user_message(self, text: str) -> None:
        entry = self._show_user_bubble(text)
        self.dock_widget.mark_rewind_point(entry, self.conversation.next_place)

    def _show_user_bubble(self, text: str) -> int:
        # The steps so far are written first: they come before the message, and so does its place.
        self.conversation.keep_trace()
        return self.dock_widget.add_user_message(text)

    def shutdown(self) -> None:
        self.conversation.save()
        self.agent.shutdown()
        self.compaction.stop()
        self.naming.stop()

    def _push_message(self, text: str, level: Any) -> None:
        self.iface.messageBar().pushMessage("AI Agent", text, level=level, duration=MESSAGE_DURATION_SEC)


def _is_configured() -> bool:
    return is_configured()
