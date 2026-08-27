from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.layout.pages import current_page_mm, layout_manager


class ListLayoutsTool(BaseTool):
    name = "list_layouts"
    description = "List the print layouts of the project with their page sizes in millimetres."
    skill = "layout"
    safety = SAFETY_READ
    examples = ["Which layouts does the project have?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the project layouts.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        described = []
        for layout in layout_manager().printLayouts():
            width, height = current_page_mm(layout)
            described.append({"name": layout.name(), "page_mm": [width, height]})
        return {"layouts": described, "count": len(described)}
