import os
import time
from collections.abc import Callable

from ai_agent.core.state.session import Session
from ai_agent.qgis_tools.common.persistence import atomic_write_json, backup_path, read_json
from ai_agent.qgis_tools.common.project_identity import project_identity

FOLDER_NAME = "ai_agent_sessions"
SUFFIX = ".json"
MAX_SESSIONS = 60
DAY_SECONDS = 86400


class SessionStore:
    def __init__(self, root: str | None = None):
        self._root = root or default_root()
        self.on_failure: Callable[[str], None] | None = None

    def save(self, session: Session) -> None:
        if session.is_empty:
            return
        path = self._path(session.identifier)
        is_new = not os.path.exists(path)
        try:
            os.makedirs(self._root, exist_ok=True)
            atomic_write_json(path, session.to_dict())
        except OSError as error:
            self._failed(error.strerror or str(error))
            return
        except (ValueError, TypeError) as error:
            # Raised out of a Qt slot, it would break this save and every later one.
            self._failed(str(error))
            return
        if is_new:
            self._trim()

    def _failed(self, reason: str) -> None:
        if self.on_failure is not None:
            self.on_failure(reason)

    def load(self, identifier: str) -> Session | None:
        loaded = read_json(self._path(identifier))
        return Session.from_dict(loaded) if isinstance(loaded, dict) else None

    def delete(self, identifier: str) -> None:
        path = self._path(identifier)
        for candidate in (path, backup_path(path)):
            try:
                os.remove(candidate)
            except OSError:
                continue

    def prune(self, days: int, keep: str = "") -> int:
        if days <= 0:
            return 0
        cutoff = time.time() - days * DAY_SECONDS
        stale = [session for session in self._all() if session.updated < cutoff and session.identifier != keep]
        for session in stale:
            self.delete(session.identifier)
        return len(stale)

    def usage(self) -> tuple[int, int]:
        names = self._names()
        size = 0
        for name in names:
            path = os.path.join(self._root, name)
            for candidate in (path, backup_path(path)):
                try:
                    size += os.path.getsize(candidate)
                except OSError:
                    continue
        return len(names), size

    def erase(self) -> None:
        for name in self._names():
            self.delete(name[: -len(SUFFIX)])

    def recent(self, project: str) -> list[Session]:
        sessions = [item for item in self._all() if item.project == project]
        sessions.sort(key=_newest_first, reverse=True)
        return sessions

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
        sessions.sort(key=_newest_first, reverse=True)
        for session in sessions[MAX_SESSIONS:]:
            self.delete(session.identifier)

    def _path(self, identifier: str) -> str:
        return os.path.join(self._root, f"{identifier}{SUFFIX}")


def _newest_first(session: Session) -> tuple[float, float, str]:
    return (session.updated, session.created, session.identifier)


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

    return project_identity(QgsProject.instance())
