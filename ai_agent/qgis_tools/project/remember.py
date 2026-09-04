from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.project.notes import MAX_NOTE_CHARS, NoteStore

SCOPE_NOTE = "Remembered for this project only. It comes back on every future conversation about the same project."
NOTHING_FORGOTTEN = "No note matches that text exactly — read them with list_notes first."


class RememberTool(BaseTool):
    name = "remember"
    description = (
        "Store a durable fact about this project — what a cryptic field means, "
        "which CRS the client wants, a naming convention. It is pinned into "
        "your context in every future conversation about this project. Use it "
        "when the user says to remember something, or states a fact that will "
        "obviously matter next time."
    )
    skill = "project"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "One fact per note, short and self-contained",
        "Facts about the user's project, not about how to use QGIS",
    ]
    examples = ["Remember that POP2020 is the 2020 population", "Note that we always export in EPSG:3857"]
    params_schema = [
        {
            "name": "note",
            "type": "string",
            "description": f"The fact, under {MAX_NOTE_CHARS} characters, written so it makes sense on its own",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        note = str(params.get("note") or "").strip()
        if not note:
            raise ValueError("The note is empty — there is nothing to remember.")
        if len(note) > MAX_NOTE_CHARS:
            raise ValueError(f"A note must stay under {MAX_NOTE_CHARS} characters; this one is {len(note)}.")
        prepared = dict(params)
        prepared["note"] = note
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Remembering: {0}").format(str(params.get("note") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        notes = NoteStore().remember(str(params.get("note") or ""))
        return {"remembered": params.get("note"), "notes_kept": len(notes), "note": SCOPE_NOTE}


class ListNotesTool(BaseTool):
    name = "list_notes"
    description = "Show everything remembered about this project."
    skill = "project"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["What do you remember about this project?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading what is remembered about this project.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        notes = NoteStore().notes()
        return {"notes": notes, "count": len(notes)}


class ForgetTool(BaseTool):
    name = "forget"
    description = "Remove one remembered fact about this project, matched exactly."
    skill = "project"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["The text must match a stored note exactly (see list_notes)"]
    examples = ["Forget that POP2020 note"]
    params_schema = [
        {
            "name": "note",
            "type": "string",
            "description": "The note to remove, exactly as list_notes shows it",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        note = str(params.get("note") or "").strip()
        if note not in NoteStore().notes():
            raise ValueError(NOTHING_FORGOTTEN)
        prepared = dict(params)
        prepared["note"] = note
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Forgetting: {0}").format(str(params.get("note") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        removed = NoteStore().forget(str(params.get("note") or ""))
        if not removed:
            raise ValueError(NOTHING_FORGOTTEN)
        return {"forgotten": params.get("note"), "notes_kept": len(NoteStore().notes())}
