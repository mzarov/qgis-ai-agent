from typing import Any

from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ai_agent.core.llm.context_window import detect
from ai_agent.core.llm.probe import probe


class ProbeThread(QThread):
    completed = pyqtSignal(bool, str)
    window_found = pyqtSignal(int)

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
        if self._cancelled:
            return
        self.completed.emit(ok, message)
        if ok:
            # A model that answers is worth asking how much it can read; stored on the main thread.
            window = detect({**self._overrides, "feedback_override": self._feedback})
            if window and not self._cancelled:
                self.window_found.emit(window)
