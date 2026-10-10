"""Conversations by name: the model names a new one after its first answer; the user renames and deletes.

The model is asked once per conversation, and only while the title is still the start
of the first message: a title the user chose is never overwritten.
"""

from collections.abc import Callable

from ai_agent.core.agent.titling import Titler
from ai_agent.core.state.conversation import ConversationState


class SessionNaming:
    def __init__(self, conversation: Callable[[], ConversationState], renamed: Callable[[], None] = lambda: None):
        self._conversation = conversation
        self._renamed = renamed
        self._titler = Titler()
        self._titler.finished.connect(self._on_named)
        self._asked: set[str] = set()
        self._scope = ""

    def after_answer(self) -> None:
        """Ask for a name once the conversation has its first exchange."""
        conversation = self._conversation()
        identifier = conversation.session_identifier
        if conversation.named or identifier in self._asked or self._titler.is_running:
            return
        request = next((m["content"] for m in conversation.messages if m["role"] == "user"), "")
        answer = next((m["content"] for m in conversation.messages if m["role"] == "assistant"), "")
        if not request or not answer:
            return
        self._asked.add(identifier)
        self._scope = identifier
        self._titler.start(request, answer)

    def stop(self) -> None:
        self._titler.stop()

    def _on_named(self, title: str, read: int, written: int) -> None:
        conversation = self._conversation()
        if conversation.session_identifier != self._scope or conversation.named:
            return
        conversation.rename(self._scope, title)
        conversation.count_turn(0, read + written)
        self._renamed()
