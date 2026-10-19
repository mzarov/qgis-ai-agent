from typing import Any

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ai_agent.core.agent.request import build_overrides
from ai_agent.core.agent.turn_thread import TurnThreadOwner

TITLE_SYSTEM = (
    "Name this conversation between a QGIS user and an AI agent in two to five words, in the "
    "language of the user's message, the way a chat list shows it: the topic, not a sentence. "
    "Reply with the title only — no quotes, no full stop."
)
EXCERPT_CHARS = 1200
TITLE_CHARS = 48
TRIMMED = " \"'«»“”„.:;!"


def clean_title(text: str) -> str:
    line = next((part for part in str(text or "").splitlines() if part.strip()), "")
    return line.strip().strip(TRIMMED).strip()[:TITLE_CHARS].strip()


class Titler(QObject):
    finished = pyqtSignal(str, int, int)

    def __init__(self) -> None:
        super().__init__()
        self._turn = TurnThreadOwner()

    @property
    def is_running(self) -> bool:
        return self._turn.is_running

    def start(self, request: str, answer: str) -> bool:
        if self.is_running or not request.strip():
            return False
        exchange = f"User:\n{request[:EXCERPT_CHARS]}\n\nAgent:\n{answer[:EXCERPT_CHARS]}"
        messages = [{"role": "system", "content": TITLE_SYSTEM}, {"role": "user", "content": exchange}]
        self._turn.start(messages, [], build_overrides(), self._on_turn, self._on_error)
        return True

    def stop(self) -> None:
        self._turn.detach(self._on_turn, self._on_error)
        self._turn.stop()

    def _on_turn(self, turn: Any) -> None:
        self._turn.release()
        title = clean_title(getattr(turn, "text", ""))
        if title:
            self.finished.emit(title, int(turn.input_tokens or 0), int(turn.output_tokens or 0))

    def _on_error(self, _message: str) -> None:
        self._turn.release()
