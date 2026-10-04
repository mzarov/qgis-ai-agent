from typing import Any

from qgis.core import Qgis

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.context.project import layer_choices
from ai_agent.core.llm.client import is_local
from ai_agent.core.orchestrator import attaching
from ai_agent.core.orchestrator.compacting import SessionCompaction
from ai_agent.core.orchestrator.contracts import DockWidgetContract
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
from ai_agent.core.orchestrator.presentation import is_configured
from ai_agent.core.orchestrator.project_lifecycle import ProjectLifecycleMixin
from ai_agent.core.orchestrator.run_events import RunEventsMixin
from ai_agent.core.orchestrator.sessions import SessionsMixin
from ai_agent.core.orchestrator.slash import available_names, choices, is_known_skill, parse_slash, prompt_for
from ai_agent.core.privacy import endpoint_label
from ai_agent.core.settings import (
    get_api_url,
    get_data_sharing_consent,
    get_model,
    get_planning,
    get_work_mode,
    set_data_sharing_consent,
)
from ai_agent.core.state.conversation import ConversationState
from ai_agent.i18n import tr


class CoreOrchestrator(SessionsMixin, PlanMixin, RunEventsMixin, ProjectLifecycleMixin):
    """Wires the dock to the agent loop. The mixins hold the rest: sessions, plans, run events, projects."""

    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.conversation = ConversationState()
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
        self._apply_scope: tuple[str, str] | None = None
        self._invalidated_scope: tuple[str, str] | None = None
        self._deferred_interrupted_outcome = ""
        self._last_request = ""
        self.compaction = SessionCompaction(self.dock_widget, lambda: self.conversation)
        self.naming = SessionNaming(lambda: self.conversation)
        self._connect_agent()
        self.dock_widget.set_session_source(self.conversation.recent)
        self.refresh_configured()

    def refresh_configured(self) -> None:
        self.dock_widget.set_configured(_is_configured())
        self.dock_widget.set_model(get_model() if _is_configured() else "")
        self.dock_widget.set_work_mode(get_work_mode())
        self.dock_widget.set_skill_source(choices)
        self.dock_widget.set_layer_source(layer_choices)
        self.compaction.refresh()

    def _connect_agent(self) -> None:
        self.agent.tool_started.connect(self.on_tool_started)
        self.agent.tool_finished.connect(self.on_tool_finished)
        self.agent.tool_queued.connect(self.on_tool_queued)
        self.agent.tool_rejected.connect(self.on_tool_rejected)
        self.agent.skill_loaded.connect(self.on_skill_loaded)
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
        self.agent.busy_changed.connect(self.dock_widget.set_busy)
        self.agent.turn_counted.connect(self.on_turn_counted)
        self.agent.answer_chunk.connect(self.dock_widget.add_stream_chunk)
        self.agent.thinking_chunk.connect(self.dock_widget.add_thinking_chunk)

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
        """Show `shown`, then run `prompt`; `request` is what the user asked, for the check after Apply."""
        self.dock_widget.add_user_message(shown)
        self._drop_pending_plan()
        planning = get_planning()

        def begin() -> None:
            history = self.conversation.window()
            self.conversation.add("user", shown)
            self._last_request = request
            self.agent.start(prompt, history, skills=skills, images=images, planning=planning)

        # The new request is not part of what gets compacted: it rides on the summary.
        def stopped() -> None:
            # The request is on screen already: keep it in the saved conversation too.
            self.conversation.add("user", shown)

        if not (self.compaction.needed() and self.compaction.start(after=begin, cancelled=stopped)):
            begin()

    def on_compact(self) -> None:
        if (
            self.agent.is_running
            or bool(getattr(self.agent, "is_applying", False))
            or self.agent.has_pending_writes
            or self.agent.is_awaiting_answer
        ):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
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
        if not self.dock_widget.confirm_data_sharing(endpoint_label(url)):
            self.dock_widget.add_system_message(DATA_SHARING_DECLINED)
            return False
        set_data_sharing_consent(True, url)
        return True

    def _answer(self, text: str) -> None:
        if not self._confirm_first_send(getattr(self.agent, "endpoint", None)):
            return
        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self.conversation.add("user", text)
        self.agent.answer(text)

    def _interject(self, text: str) -> None:
        if not self.agent.interject(text):
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self.dock_widget.add_system_message(INTERJECTED)
        self.conversation.add("user", text)

    def shutdown(self) -> None:
        self.conversation.save()
        self.agent.stop()
        self.compaction.stop()
        self.naming.stop()

    def _push_message(self, text: str, level) -> None:
        self.iface.messageBar().pushMessage("AI Agent", text, level=level, duration=MESSAGE_DURATION_SEC)


def _is_configured() -> bool:
    return is_configured()
