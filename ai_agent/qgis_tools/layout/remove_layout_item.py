from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.layout.items import find_item, item_kind
from ai_agent.qgis_tools.layout.pages import find_layout


class RemoveLayoutItemTool(BaseTool):
    name = "remove_layout_item"
    description = "Remove one item from a print layout by its id. The layout itself stays."
    skill = "layout"
    safety = SAFETY_WRITE
    constraints = ["The item id must exist (see describe_layout)"]
    examples = ["Drop the second label", "Remove the scale bar"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
        {
            "name": "item_id",
            "type": "string",
            "description": "Item id exactly as in describe_layout",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        find_item(layout, params.get("item_id") or "")
        prepared = dict(params)
        prepared["layout_name"] = layout.name()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        item_id = (params.get("item_id") or "").strip()
        name = (params.get("layout_name") or "").strip()
        return tr("Removing item '{0}' from layout '{1}'.").format(item_id, name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        item = find_item(layout, params.get("item_id") or "")
        kind = item_kind(item)
        layout.removeLayoutItem(item)
        return {"layout": layout.name(), "removed": params.get("item_id"), "type": kind}
