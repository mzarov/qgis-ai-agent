from typing import Any

from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ai_agent.core.llm.context_window import detect
from ai_agent.core.llm.probe import probe, sees_images


class ProbeThread(QThread):
    completed = pyqtSignal(bool, str)
    window_found = pyqtSignal(int)
    images_checked = pyqtSignal(bool)

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
        overrides = {**self._overrides, "feedback_override": self._feedback}
        ok, message = probe(overrides)
        if self._cancelled:
            return
        self.completed.emit(ok, message)
        if not ok:
            return
        # Emitted after `completed`: the main thread resets what it knew there before storing these.
        window = detect(overrides)
        if window and not self._cancelled:
            self.window_found.emit(window)
        sees = None if self._cancelled else sees_images(overrides)
        if sees is not None and not self._cancelled:
            self.images_checked.emit(sees)
