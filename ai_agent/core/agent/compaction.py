from typing import Any

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent.request import build_overrides
from ai_agent.core.agent.turn_thread import TurnThreadOwner
from ai_agent.core.llm.turns import ModelTurn

COMPACT_SYSTEM = (
    "You are compacting a conversation between a QGIS user and an AI agent that works in their "
    "project, so that it fits the model's context window. Write a handoff summary for the model "
    "that will continue the conversation. Include:\n"
    "- what the user wants, in their words where the wording matters;\n"
    "- what was done in the project, with exact layer, field, file and layout names;\n"
    "- decisions, constraints and preferences the user stated;\n"
    "- facts that were looked up and are still needed (CRS, field names, counts);\n"
    "- what is unfinished or was asked for next.\n"
    "Write in the language of the user's messages. Be concise and factual: plain text, short "
    "lines, no more than about 400 words, nothing invented."
)
COMPACT_REQUEST = "Write the handoff summary now."
EMPTY_SUMMARY = "The model returned an empty summary."
CHARS_PER_TOKEN = 4
WIDE_CHARS_PER_TOKEN = 2.5


def estimated_tokens(messages: list[dict[str, Any]]) -> int:
    text = "".join(str(message.get("content") or "") for message in messages)
    latin = sum(1 for character in text if character.isascii())
    return int(latin / CHARS_PER_TOKEN + (len(text) - latin) / WIDE_CHARS_PER_TOKEN)


class Compactor(QObject):  # type: ignore[misc]
    finished = pyqtSignal(str, int, int)
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._turn = TurnThreadOwner()

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    def start(self, history: list[dict[str, Any]]) -> bool:
        if self.is_running or not history:
            return False
        messages = [
            {"role": "system", "content": COMPACT_SYSTEM},
            *history,
            {"role": "user", "content": COMPACT_REQUEST},
        ]
        self._turn.start(messages, [], build_overrides(), self._on_turn, self._on_error)
        return True

    def abort(self) -> None:
        self._turn.detach(self._on_turn, self._on_error)

    def stop(self) -> None:
        # Detach first: an answer already queued must not reach a dock that unload deleted.
        self._turn.detach(self._on_turn, self._on_error)
        self._turn.stop()

    def _on_turn(self, turn: ModelTurn) -> None:
        self._turn.release()
        summary = str(getattr(turn, "text", "") or "").strip()
        if not summary:
            self.failed.emit(EMPTY_SUMMARY)
            return
        self.finished.emit(summary, int(turn.input_tokens or 0), int(turn.output_tokens or 0))

    def _on_error(self, message: str) -> None:
        self._turn.release()
        self.failed.emit(message)
