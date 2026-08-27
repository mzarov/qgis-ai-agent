from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.layout.items import describe_item, layout_items
from qgis_ai_agent.qgis_tools.layout.pages import current_page_mm, find_layout

OVERLAP_NOTE = (
    "Positions and sizes are in millimetres from the top-left page corner. "
    "To judge the visual result, call render_layout and look at the image."
)


class DescribeLayoutTool(BaseTool):
    name = "describe_layout"
    description = (
        "Show the contents of a print layout: page size and every item with its "
        "id, type, position and size in millimetres. Call it before moving or "
        "changing items."
    )
    skill = "layout"
    safety = SAFETY_READ
    constraints = ["The layout must exist (see list_layouts)"]
    examples = ["What is on the A4 layout?", "Where does the legend sit?"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = (params.get("layout_name") or "").strip()
        return tr("Reading layout '{0}'.").format(name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        width, height = current_page_mm(layout)
        items = [describe_item(item) for item in layout_items(layout)]
        return {
            "name": layout.name(),
            "page_mm": [width, height],
            "items": items,
            "item_count": len(items),
            "note": OVERLAP_NOTE,
        }
