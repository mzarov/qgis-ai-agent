from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.journal import record_run
from ai_agent.core.settings import get_write_run_journal

LOG_TAG = "AI Agent"


class RunJournal:
    """The optional Markdown record of one run: written once, and only after something was applied."""

    def __init__(self) -> None:
        self.prompt = ""
        self.applied = 0
        self.saved = False

    def begin(self, prompt: str) -> None:
        self.prompt = prompt
        self.applied = 0
        self.saved = False

    def count(self, successful: int) -> None:
        self.applied += successful

    def write(self, entries: list[dict[str, Any]], outcome: str) -> str:
        """Return the file path, or "" when nothing was written."""
        if not self.applied or self.saved or not get_write_run_journal():
            return ""
        try:
            path = record_run(self.prompt, entries, outcome, self.applied)
        except Exception as err:
            QgsMessageLog.logMessage(f"Journal not written: {err}", LOG_TAG, Qgis.MessageLevel.Warning)
            return ""
        self.saved = True
        QgsMessageLog.logMessage(f"Run journal: {path}", LOG_TAG, Qgis.MessageLevel.Info)
        return path
