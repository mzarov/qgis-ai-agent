"""The user's own notes for the Personalisation page: ui/ never touches the tool layer's note store."""

from ai_agent.qgis_tools.project.notes import MAX_NOTE_CHARS, MAX_NOTES, NoteStore

__all__ = ["MAX_NOTES", "MAX_NOTE_CHARS", "save_user_notes", "user_notes"]


def user_notes() -> list[str]:
    try:
        return NoteStore().user_notes()
    except Exception:
        return []


def save_user_notes(notes: list[str]) -> None:
    """Store the notes as edited on the page; ValueError with the reason when the profile is not writable."""
    NoteStore().replace_user_notes(notes)
