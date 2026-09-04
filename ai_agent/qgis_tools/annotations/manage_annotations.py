from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.annotations.store import list_items, remove_item
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, SAFETY_WRITE, BaseTool


class ListAnnotationsTool(BaseTool):
    name = "list_annotations"
    description = "List the annotations on the map with their ids, kinds and texts."
    skill = "annotations"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["What notes are on the map?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the map annotations.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        items = list_items()
        return {"annotations": items, "count": len(items)}


class RemoveAnnotationTool(BaseTool):
    name = "remove_annotation"
    description = "Remove one annotation from the map by its id (see list_annotations)."
    skill = "annotations"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["The id must exist — read list_annotations first"]
    examples = ["Remove that note"]
    params_schema = [
        {"name": "id", "type": "string", "description": "Annotation id from list_annotations", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Removing annotation {0}.").format(str(params.get("id") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        item_id = str(params.get("id") or "").strip()
        if not item_id:
            raise ValueError("The annotation id is empty — read list_annotations first.")
        remove_item(item_id)
        return {"removed": item_id}
