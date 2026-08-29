from typing import Any

from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QThread, pyqtSignal

from qgis_ai_agent.core.llm.probe import probe


class ProbeThread(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, overrides: dict[str, Any], parent: Any = None):
        super().__init__(parent)
        self._overrides = dict(overrides)
        self._feedback = QgsFeedback()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.requestInterruption()
        self._feedback.cancel()

    def run(self) -> None:
        ok, message = probe({**self._overrides, "feedback_override": self._feedback})
        if not self._cancelled:
            self.completed.emit(ok, message)
