from qgis.PyQt.QtCore import QThread, pyqtSignal


class ModelTurnThread(QThread):
    """
    Поток для одного хода агента: сетевой вызов уходит из главного потока,
    а результат приходит сигналом обратно в главный, где безопасно трогать PyQGIS.
    """

    finished_turn = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, messages, tool_schemas, overrides, timeout=120, parent=None):
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
            self.finished_turn.emit(turn)
        except Exception as err:
            self.error.emit(str(err))
