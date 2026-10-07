from typing import Any

from ai_agent.config.personal import load as load_profile
from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.project.notes import MAX_NOTE_CHARS, USER_KEY, NoteStore

SCOPE_NOTE = "Remembered for this project only. It comes back on every future conversation about the same project."
USER_SCOPE_NOTE = "Remembered about the user. It comes back in every future conversation, in any project."
ABOUT_PROJECT = "project"
ABOUT_USER = "user"
OWN_NOTES_OFF = (
    "The user turned off notes you add yourself (Settings → Personalisation → Memory). "
    "Do not store it; if it matters, tell them they can add it there."
)
NOTHING_FORGOTTEN = "No note matches that text exactly — read them with list_notes first."


class RememberTool(BaseTool):
    name = "remember"
    description = (
        "Store a durable fact. about=project (default): what a cryptic field means, which CRS the client "
        "wants, a naming convention — pinned into every future conversation about this project. "
        "about=user: a fact about the user themselves — their organisation, usual area, preferred formats — "
        "pinned into every future conversation in any project. Use it when the user says to remember "
        "something, or states a fact that will obviously matter next time."
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
        {
            "name": "about",
            "type": "string",
            "enum": [ABOUT_PROJECT, ABOUT_USER],
            "description": "project (default) or user",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        note = str(params.get("note") or "").strip()
        if not note:
            raise ValueError("The note is empty — there is nothing to remember.")
        about = str(params.get("about") or ABOUT_PROJECT).strip()
        if about not in (ABOUT_PROJECT, ABOUT_USER):
            raise ValueError(f"about must be {ABOUT_PROJECT} or {ABOUT_USER}.")
        if about == ABOUT_USER and not load_profile().own_notes:
            raise ValueError(OWN_NOTES_OFF)
        if len(note) > MAX_NOTE_CHARS:
            raise ValueError(f"A note must stay under {MAX_NOTE_CHARS} characters; this one is {len(note)}.")
        prepared = dict(params)
        prepared["note"] = note
        prepared["about"] = about
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Remembering: {0}").format(str(params.get("note") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        about_user = params.get("about") == ABOUT_USER
        key = USER_KEY if about_user else None
        notes = NoteStore().remember(str(params.get("note") or ""), key)
        scope = USER_SCOPE_NOTE if about_user else SCOPE_NOTE
        return {"remembered": params.get("note"), "notes_kept": len(notes), "note": scope}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        store = NoteStore()
        kept = store.user_notes() if params.get("about") == ABOUT_USER else store.notes()
        return str(params.get("note") or "").strip() in kept


class ListNotesTool(BaseTool):
    name = "list_notes"
    description = "Show everything remembered: about this project, and about the user in every project."
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
        store = NoteStore()
        notes, about_user = store.notes(), store.user_notes()
        return {"notes": notes, "about_user": about_user, "count": len(notes) + len(about_user)}


class ForgetTool(BaseTool):
    name = "forget"
    description = "Remove one remembered fact, about this project or about the user, matched exactly."
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
        store = NoteStore()
        if note not in store.notes() and note not in store.user_notes():
            raise ValueError(NOTHING_FORGOTTEN)
        prepared = dict(params)
        prepared["note"] = note
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Forgetting: {0}").format(str(params.get("note") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        note = str(params.get("note") or "")
        store = NoteStore()
        removed = store.forget(note) or store.forget(note, USER_KEY)
        if not removed:
            raise ValueError(NOTHING_FORGOTTEN)
        return {"forgotten": params.get("note"), "notes_kept": len(store.notes()) + len(store.user_notes())}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        note = str(params.get("note") or "").strip()
        store = NoteStore()
        return note not in store.notes() and note not in store.user_notes()
