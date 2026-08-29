import json
import os
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.qgis_tools.project.tree import project

LOG_TAG = "AI Agent"
FOLDER_NAME = "ai_agent_sessions"
NO_PROJECT_KEY = "no-project"
FILE_NAME = "project_notes.json"
MAX_NOTES = 40
MAX_NOTE_CHARS = 300


def current_project_key() -> str:
    try:
        path = (project().fileName() or "").strip()
    except Exception:
        path = ""
    return os.path.basename(path) or NO_PROJECT_KEY


def default_root() -> str:
    try:
        from qgis.core import QgsApplication

        return os.path.join(QgsApplication.qgisSettingsDirPath(), FOLDER_NAME)
    except Exception:
        return os.path.join(os.path.expanduser("~"), FOLDER_NAME)


class NoteStore:
    def __init__(self, root: str | None = None):
        self._root = root or default_root()

    def path(self) -> str:
        return os.path.join(self._root, FILE_NAME)

    def all_notes(self) -> dict[str, list[str]]:
        try:
            with open(self.path(), encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def notes(self, project_key: str | None = None) -> list[str]:
        key = project_key or current_project_key()
        found = self.all_notes().get(key)
        return [str(item) for item in found] if isinstance(found, list) else []

    def remember(self, text: str, project_key: str | None = None) -> list[str]:
        note = (text or "").strip()
        if not note:
            raise ValueError("The note is empty — there is nothing to remember.")
        if len(note) > MAX_NOTE_CHARS:
            raise ValueError(f"A note must stay under {MAX_NOTE_CHARS} characters; this one is {len(note)}.")
        key = project_key or current_project_key()
        stored = self.all_notes()
        kept = [item for item in stored.get(key, []) if item != note]
        kept.append(note)
        stored[key] = kept[-MAX_NOTES:]
        self._write(stored)
        return stored[key]

    def forget(self, text: str, project_key: str | None = None) -> bool:
        note = (text or "").strip()
        key = project_key or current_project_key()
        stored = self.all_notes()
        kept = [item for item in stored.get(key, []) if item != note]
        if len(kept) == len(stored.get(key, [])):
            return False
        stored[key] = kept
        self._write(stored)
        return True

    def _write(self, payload: dict[str, Any]) -> None:
        try:
            os.makedirs(self._root, exist_ok=True)
            with open(self.path(), "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=1)
        except OSError as failure:
            QgsMessageLog.logMessage(f"Could not write project notes: {failure}", LOG_TAG, Qgis.Warning)
