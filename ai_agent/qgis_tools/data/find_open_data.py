from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.data.catalogue import describe, search

NOTHING = "No dataset in the catalogue matches. Call find_open_data with no query to see all of them."


SHOWN_TITLES = 3


class FindOpenDataTool(BaseTool):
    name = "find_open_data"
    description = (
        "Look up the open datasets the plugin can fetch: world vector layers, administrative "
        "boundaries, satellite imagery, elevation, land cover, surface water. Answers from a "
        "built-in catalogue without going online, with how to load each one."
    )
    skill = "data"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Where can I get a satellite image of this area?", "Find district boundaries for Kenya"]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "What the user needs, in English words: 'elevation', 'satellite image', 'regions'",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        query = str(params.get("query") or "").strip()
        if not query:
            return tr("Listing the open datasets.")
        return tr("Looking up open data: {0}.").format(query)

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        titles = [str(item.get("title") or "") for item in payload.get("datasets") or []]
        if not titles:
            return tr("Nothing found")
        shown = ", ".join(titles[:SHOWN_TITLES])
        return shown if len(titles) <= SHOWN_TITLES else f"{shown} +{len(titles) - SHOWN_TITLES}"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        found = search(str(params.get("query") or ""))
        if not found:
            return {"datasets": [], "note": NOTHING}
        return {"datasets": [describe(item) for item in found]}
