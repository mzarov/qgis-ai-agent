import time
from collections.abc import Sequence

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.journal import record_run
from ai_agent.core.agent.transcript import TranscriptEntry
from ai_agent.core.settings import get_write_run_journal

LOG_TAG = "AI Agent"
CLOCK = time.monotonic


class RunJournal:
    def __init__(self) -> None:
        self.prompt = ""
        self.applied = 0
        self.saved = False
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
        self._asked = CLOCK()

    def answered(self, prompt_tokens: int, completion_tokens: int) -> None:
        seconds = CLOCK() - self._asked if self._asked else 0.0
        self.requests.append((max(0, prompt_tokens), max(0, completion_tokens), max(0.0, seconds)))
        self._asked = 0.0

    def write(self, entries: Sequence[TranscriptEntry], outcome: str) -> str:
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
