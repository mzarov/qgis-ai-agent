from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QThread, pyqtSignal

from qgis_ai_agent.core.llm.client import DEFAULT_TIMEOUT
from qgis_ai_agent.core.llm.transport import call_model


class ModelTurnThread(QThread):
    finished_turn = pyqtSignal(object)
    chunk = pyqtSignal(str)
    thinking = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, messages, tool_schemas, overrides, timeout=DEFAULT_TIMEOUT, parent=None):
        super().__init__(parent)
        self._messages = messages
        self._tool_schemas = tool_schemas
        self._overrides = dict(overrides or {})
        self._feedback = QgsFeedback()
        self._overrides["feedback_override"] = self._feedback
        self._timeout = timeout

    def cancel(self) -> None:
        self.requestInterruption()
        self._feedback.cancel()

    def _emit_chunk(self, text: str) -> None:
        if not self.isInterruptionRequested():
            self.chunk.emit(text)

    def _emit_thinking(self, text: str) -> None:
        if not self.isInterruptionRequested():
            self.thinking.emit(text)

    def run(self) -> None:
        try:
            turn = call_model(
                self._messages,
                self._tool_schemas,
                overrides=self._overrides,
                timeout=self._timeout,
                on_chunk=self._emit_chunk,
                on_thinking=self._emit_thinking,
            )
        except Exception as err:
            if not self.isInterruptionRequested():
                self.error.emit(str(err))
            return
        if not self.isInterruptionRequested():
            self.finished_turn.emit(turn)
