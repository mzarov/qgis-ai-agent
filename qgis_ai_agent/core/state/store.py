import json
import os

from qgis_ai_agent.core.state.session import Session

FOLDER_NAME = "qgis_ai_agent_sessions"
SUFFIX = ".json"
MAX_SESSIONS = 60


class SessionStore:
    def __init__(self, root: str | None = None):
        self._root = root or default_root()

    def save(self, session: Session) -> None:
        if session.is_empty or not self._ensure_root():
            return
        path = self._path(session.identifier)
        is_new = not os.path.exists(path)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(session.to_dict(), handle, ensure_ascii=False)
        except OSError:
            return
        if is_new:
            self._trim()

    def load(self, identifier: str) -> Session | None:
        try:
            with open(self._path(identifier), encoding="utf-8") as handle:
                return Session.from_dict(json.load(handle))
        except (OSError, ValueError):
            return None

    def delete(self, identifier: str) -> None:
        try:
            os.remove(self._path(identifier))
        except OSError:
            return

    def recent(self, project: str, limit: int = 20) -> list[Session]:
        sessions = [item for item in self._all() if item.project == project]
        sessions.sort(key=lambda item: item.updated, reverse=True)
        return sessions[:limit]

    def _all(self) -> list[Session]:
        sessions = []
        for name in self._names():
            session = self.load(name[: -len(SUFFIX)])
            if session is not None:
                sessions.append(session)
        return sessions

    def _names(self) -> list[str]:
        try:
            return [name for name in os.listdir(self._root) if name.endswith(SUFFIX)]
        except OSError:
            return []

    def _trim(self) -> None:
        sessions = self._all()
        if len(sessions) <= MAX_SESSIONS:
            return
        sessions.sort(key=lambda item: item.updated, reverse=True)
        for session in sessions[MAX_SESSIONS:]:
            self.delete(session.identifier)

    def _path(self, identifier: str) -> str:
        return os.path.join(self._root, f"{identifier}{SUFFIX}")

    def _ensure_root(self) -> bool:
        try:
            os.makedirs(self._root, exist_ok=True)
        except OSError:
            return False
        return True


def default_root() -> str:
    from qgis.core import QgsApplication

    try:
        base = QgsApplication.qgisSettingsDirPath()
    except Exception:
        base = ""
    if not isinstance(base, str) or not base:
        base = os.path.expanduser("~")
    return os.path.join(base, FOLDER_NAME)


def current_project_key() -> str:
    from qgis.core import QgsProject

    from qgis_ai_agent.core.state.session import NO_PROJECT

    try:
        path = QgsProject.instance().fileName()
    except Exception:
        path = ""
    if not isinstance(path, str):
        return NO_PROJECT
    return path.strip() or NO_PROJECT
