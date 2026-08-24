from qgis.PyQt.QtCore import QThread, pyqtSignal

DEFAULT_TIMEOUT = 120


class ModelTurnThread(QThread):
    finished_turn = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, messages, tool_schemas, overrides, timeout=DEFAULT_TIMEOUT, parent=None):
        super().__init__(parent)
        self._messages = messages
        self._tool_schemas = tool_schemas
        self._overrides = overrides or {}
        self._timeout = timeout

    def run(self):
        from qgis_ai_agent.core.llm.transport import call_model

        try:
            turn = call_model(
                self._messages,
                self._tool_schemas,
                overrides=self._overrides,
                timeout=self._timeout,
            )
        except Exception as err:
            if not self.isInterruptionRequested():
                self.error.emit(str(err))
            return
        if not self.isInterruptionRequested():
            self.finished_turn.emit(turn)
