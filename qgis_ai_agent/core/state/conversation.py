from qgis_ai_agent.core.state.history import HistoryStore
from qgis_ai_agent.core.state.session import Session
from qgis_ai_agent.core.state.store import SessionStore, current_project_key

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

    def window(self) -> list[dict[str, str]]:
        return self._history.get()

    def add(self, role: str, text: str) -> None:
        self._history.add(role, text)
        self._session.add(role, text)
        self._store.save(self._session)

    def save(self) -> None:
        self._store.save(self._session)

    def recent(self) -> list[tuple[str, str]]:
        return [(session.identifier, session.display_title()) for session in self._store.recent(current_project_key())]

    def start_new(self) -> None:
        self.save()
        self._adopt(Session.create(current_project_key()))

    def restore(self, identifier: str) -> bool:
        session = self._store.load(identifier)
        if session is None:
            return False
        self.save()
        self._adopt(session)
        return True

    def _adopt(self, session: Session) -> None:
        self._session = session
        self._history = HistoryStore(max_messages=self._limit)
        for message in session.messages[-self._limit :]:
            self._history.add(message["role"], message["content"])
