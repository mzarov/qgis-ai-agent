from qgis.PyQt.QtCore import QThread, pyqtSignal


class LLMWorkerThread(QThread):
    """Поток для одного запроса к LLM: блокирующий вызов выполняется в run()."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, payload, parent=None):
        super().__init__(parent)
        self._payload = payload

    def run(self):
        from qgis_ai_agent.core.llm.client import chat

        messages = self._payload.get("messages") or []
        overrides = self._payload.get("overrides") or {}
        stream = self._payload.get("stream", True)
        try:
            def on_chunk(text):
                self.progress.emit(text)

            reply = chat(
                messages,
                stream=stream,
                on_chunk=on_chunk if stream else None,
                **overrides,
            )
            self.finished.emit(reply)
        except Exception as e:
            self.error.emit(str(e))
