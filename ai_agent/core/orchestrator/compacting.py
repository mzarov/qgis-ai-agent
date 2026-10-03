"""The orchestrator's half of the context window: the meter, and compacting by hand or on the way in.

Before a request the conversation is compacted when the conversation's request
size reached AUTO_COMPACT_SHARE of the model's window; the request then starts
from the summary. The chat keeps every message and gains one line saying what
was saved. A compaction belongs to the conversation it started in: switched,
stopped or unloaded midway, its answer is dropped.
"""

from collections.abc import Callable

from ai_agent.core.agent.compaction import Compactor, estimated_tokens
from ai_agent.core.llm.context_window import auto_compact_at, window_for
from ai_agent.core.orchestrator.contracts import DockWidgetContract
from ai_agent.core.orchestrator.presentation import compact_number
from ai_agent.core.settings import get_api_url, get_dialect, get_model
from ai_agent.core.state.conversation import ConversationState
from ai_agent.i18n import tr

COMPACTING = tr("Compacting the conversation…")
COMPACTED = tr("Conversation compacted · about {0} tokens saved")
NOT_COMPACTED = tr("Could not compact the conversation: {0}")
NOTHING_TO_COMPACT = tr("There is nothing to compact yet.")


class SessionCompaction:
    def __init__(self, dock: DockWidgetContract, conversation: Callable[[], ConversationState]):
        self._dock = dock
        # The orchestrator may swap its ConversationState (tests do): always ask for the current one.
        self._conversation = conversation
        self._compactor = Compactor()
        self._compactor.finished.connect(self._on_finished)
        self._compactor.failed.connect(self._on_failed)
        self._after: Callable[[], None] | None = None
        self._cancelled: Callable[[], None] | None = None
        self._scope = ""
        self._upto = 0
        self._before = (0, 0)
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def window(self) -> int:
        return window_for(get_api_url() or "", get_model() or "", get_dialect() or None)

    def refresh(self) -> None:
        conversation = self._conversation()
        self._dock.set_context(
            conversation.context_tokens, self.window(), conversation.spent_tokens, conversation.requests
        )

    def needed(self) -> bool:
        conversation = self._conversation()
        return bool(conversation.window()) and conversation.context_tokens >= auto_compact_at(self.window())

    def start(
        self,
        after: Callable[[], None] | None = None,
        cancelled: Callable[[], None] | None = None,
    ) -> bool:
        """Compact now. `after` runs once it is done, worked or not; `cancelled` if it is stopped."""
        conversation = self._conversation()
        history = conversation.window()
        if self._running or not history:
            if not history and after is None:
                self._dock.add_system_message(NOTHING_TO_COMPACT)
            return False
        if not self._compactor.start(history):
            return False
        self._running = True
        self._scope = conversation.session_identifier
        self._upto = conversation.message_count
        self._before = (conversation.context_tokens, estimated_tokens(history))
        self._after, self._cancelled = after, cancelled
        self._dock.set_busy(True)
        self._dock.add_tool_message(COMPACTING)
        return True

    def cancel(self) -> None:
        """Stop a running compaction without waiting; the request that waited for it does not run."""
        if not self._running:
            return
        self._compactor.abort()
        cancelled = self._cancelled
        self._reset()
        self._dock.set_busy(False)
        if cancelled is not None:
            cancelled()
        self.refresh()

    def stop(self) -> None:
        self._compactor.stop()
        self._reset()

    def _on_finished(self, summary: str, read: int, written: int) -> None:
        conversation = self._conversation()
        if conversation.session_identifier != self._scope:
            # The user moved to another conversation meanwhile: this summary is not theirs.
            self._abandon()
            return
        used_before, history_before = self._before
        conversation.compact(summary, self._upto)
        # Only the history part of the request shrank; the system prompt and tools stay as measured.
        saved = max(0, history_before - estimated_tokens(conversation.window()))
        conversation.set_context(used_before - saved)
        conversation.count_turn(0, read + written)
        self._dock.add_system_message(COMPACTED.format(compact_number(saved)))
        self._finish()

    def _on_failed(self, message: str) -> None:
        if self._conversation().session_identifier != self._scope:
            self._abandon()
            return
        self._dock.add_system_message(NOT_COMPACTED.format(message))
        self._finish()

    def _finish(self) -> None:
        after = self._after
        self._reset()
        self._dock.set_busy(False)
        self.refresh()
        if after is not None:
            after()

    def _abandon(self) -> None:
        self._reset()
        self._dock.set_busy(False)

    def _reset(self) -> None:
        self._running = False
        self._after = None
        self._cancelled = None
