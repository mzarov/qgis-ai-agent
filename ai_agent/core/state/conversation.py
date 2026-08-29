from ai_agent.core.state.history import HistoryStore
from ai_agent.core.state.session import Session
from ai_agent.core.state.store import SessionStore, current_project_key

WINDOW_LIMIT = 14


class ConversationState:
    def __init__(self, window_limit: int = WINDOW_LIMIT, store: SessionStore | None = None):
        self._limit = window_limit
        self._store = store or SessionStore()
        self._history = HistoryStore(max_messages=window_limit)
        self._session = Session.create(current_project_key())

    @property
    def messages(self) -> list[dict[str, str]]:
        return self._session.messages

    @property
    def session_identifier(self) -> str:
        return self._session.identifier

    @property
    def project_key(self) -> str:
        return self._session.project

    def window(self) -> list[dict[str, str]]:
        return self._history.get()

    def add(self, role: str, text: str) -> None:
        self._history.add(role, text)
        self._session.add(role, text)
        self._store.save(self._session)

    def add_scoped(self, scope: tuple[str, str], role: str, text: str) -> bool:
        project, identifier = scope
        if (self.project_key, self.session_identifier) == scope:
            self.add(role, text)
            return True
        session = self._store.load(identifier)
        if session is None or session.project != project:
            return False
        session.add(role, text)
        self._store.save(session)
        return True

    def save(self) -> None:
        self._store.save(self._session)

    def recent(self) -> list[tuple[str, str]]:
        return [(session.identifier, session.display_title()) for session in self._store.recent(self.project_key)]

    def start_new(self) -> None:
        self.save()
        self._adopt(Session.create(self.project_key))

    def sync_project(self, force_new: bool = False) -> bool:
        key = current_project_key()
        if not force_new and key == self.project_key:
            return False
        self.save()
        self._adopt(Session.create(key))
        return True

    def restore(self, identifier: str) -> bool:
        session = self._store.load(identifier)
        if session is None or session.project != self.project_key:
            return False
        self.save()
        self._adopt(session)
        return True

    def _adopt(self, session: Session) -> None:
        self._session = session
        self._history = HistoryStore(max_messages=self._limit)
        for message in session.messages[-self._limit :]:
            self._history.add(message["role"], message["content"])
