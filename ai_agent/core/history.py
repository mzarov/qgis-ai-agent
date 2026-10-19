from ai_agent.core.agent import journal
from ai_agent.core.state.store import SessionStore


def usage() -> tuple[int, int]:
    conversations, size = SessionStore().usage()
    _journals, journal_size = journal.usage()
    return conversations, size + journal_size


def erase() -> None:
    SessionStore().erase()
    journal.erase()


def journals_folder() -> str:
    return journal.default_root()
