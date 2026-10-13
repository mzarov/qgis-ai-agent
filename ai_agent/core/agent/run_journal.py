import time
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.journal import record_run
from ai_agent.core.settings import get_write_run_journal

LOG_TAG = "AI Agent"
CLOCK = time.monotonic


class RunJournal:
    """The optional Markdown record of one run: written once, and only after something was applied.

    Besides the steps it keeps every model request's tokens and seconds, the two
    figures that show where a slow or expensive run went.
    """

    def __init__(self) -> None:
        self.prompt = ""
        self.applied = 0
        self.saved = False
        # (input tokens, output tokens, seconds) per model request, discarded ones included: they were billed.
        self.requests: list[tuple[int, int, float]] = []
        self._asked = 0.0

    def begin(self, prompt: str) -> None:
        self.prompt = prompt
        self.applied = 0
        self.saved = False
        self.requests = []
        self._asked = 0.0

    def count(self, successful: int) -> None:
        self.applied += successful

    def asked(self) -> None:
        """A request to the model went out; its answer's seconds count from here."""
        self._asked = CLOCK()

    def answered(self, prompt_tokens: int, completion_tokens: int) -> None:
        seconds = CLOCK() - self._asked if self._asked else 0.0
        self.requests.append((max(0, prompt_tokens), max(0, completion_tokens), max(0.0, seconds)))
        self._asked = 0.0

    def write(self, entries: list[dict[str, Any]], outcome: str) -> str:
        """Return the file path, or "" when nothing was written."""
        if not self.applied or self.saved or not get_write_run_journal():
            return ""
        try:
            path = record_run(self.prompt, entries, outcome, self.applied, requests=self.requests)
        except Exception as err:
            QgsMessageLog.logMessage(f"Journal not written: {err}", LOG_TAG, Qgis.MessageLevel.Warning)
            return ""
        self.saved = True
        QgsMessageLog.logMessage(f"Run journal: {path}", LOG_TAG, Qgis.MessageLevel.Info)
        return path
