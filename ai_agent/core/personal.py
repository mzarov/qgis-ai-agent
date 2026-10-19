from ai_agent.qgis_tools.project.notes import MAX_NOTE_CHARS, MAX_NOTES, NoteStore

__all__ = ["MAX_NOTES", "MAX_NOTE_CHARS", "save_user_notes", "user_notes"]


def user_notes() -> list[str]:
    try:
        return NoteStore().user_notes()
    except Exception:
        return []


def save_user_notes(notes: list[str]) -> None:
    NoteStore().replace_user_notes(notes)
