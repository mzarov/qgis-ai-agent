"""The kept conversations and run journals as one history: how big it is, and erasing it.

Settings → Privacy shows the size and offers to erase everything; the dialog
asks first, and the orchestrator then drops the conversation that was open
(`CoreOrchestrator.on_history_erased`).
"""

from ai_agent.core.agent import journal
from ai_agent.core.state.store import SessionStore


def usage() -> tuple[int, int]:
    """Kept conversations, and the bytes they and the run journals take on disk."""
    conversations, size = SessionStore().usage()
    _journals, journal_size = journal.usage()
    return conversations, size + journal_size


def erase() -> None:
    """Delete every kept conversation, of every project, and every run journal. Cannot be undone."""
    SessionStore().erase()
    journal.erase()


def journals_folder() -> str:
    return journal.default_root()
