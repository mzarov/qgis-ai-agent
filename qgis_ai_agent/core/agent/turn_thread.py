from typing import Any, Callable

from qgis_ai_agent.core.llm.worker import ModelTurnThread

THREAD_STOP_TIMEOUT_MS = 3000


class TurnThreadOwner:
    def __init__(self) -> None:
        self._thread: ModelTurnThread | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    def start(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        overrides: dict[str, Any],
        on_turn: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        thread = ModelTurnThread(messages, tool_schemas, overrides)
        thread.finished_turn.connect(on_turn)
        thread.error.connect(on_error)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()

    def release(self) -> None:
        self._thread = None

    def detach(self, on_turn: Callable[[Any], None], on_error: Callable[[str], None]) -> None:
        thread = self._thread
        self._thread = None
        if thread is None:
            return
        for signal, slot in ((thread.finished_turn, on_turn), (thread.error, on_error)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                continue

    def stop(self) -> None:
        thread = self._thread
        self._thread = None
        if not thread or not thread.isRunning():
            return
        thread.requestInterruption()
        if thread.wait(THREAD_STOP_TIMEOUT_MS):
            return
        thread.terminate()
        thread.wait(THREAD_STOP_TIMEOUT_MS)
