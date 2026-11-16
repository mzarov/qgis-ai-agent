from typing import Any

from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ai_agent.core.llm.context_window import detect, list_models
from ai_agent.core.llm.probe import probe, sees_images


class SettingsThread(QThread):  # type: ignore[misc]
    def __init__(self, overrides: dict[str, Any], parent: Any = None) -> None:
        super().__init__(parent)
        self._overrides = dict(overrides)
        self._feedback = QgsFeedback()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.requestInterruption()
        self._feedback.cancel()


class ProbeThread(SettingsThread):
    completed = pyqtSignal(bool, str)
    window_found = pyqtSignal(int)
    images_checked = pyqtSignal(bool)

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


class ModelListThread(SettingsThread):
    listed = pyqtSignal(list, str)

    def run(self) -> None:
        names, problem = list_models({**self._overrides, "feedback_override": self._feedback})
        if not self._cancelled:
            self.listed.emit(names, problem)
