from typing import Any

from qgis.core import QgsLayoutSize, QgsPrintLayout, QgsProject

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.layout.items import MM
from qgis_ai_agent.qgis_tools.layout.pages import (
    DEFAULT_ORIENTATION,
    DEFAULT_PAGE,
    ORIENTATIONS,
    PAGE_SIZES_MM,
    layout_names,
    page_size_mm,
)


class CreateLayoutTool(BaseTool):
    name = "create_layout"
    description = (
        "Create a new empty print layout with the given page size and "
        "orientation. Items are added afterwards with add_layout_item."
    )
    skill = "layout"
    safety = SAFETY_WRITE
    constraints = ["The layout name must be unique in the project"]
    examples = ["Create an A4 landscape layout", "Make an A3 map sheet"]
    params_schema = [
        {
            "name": "name",
            "type": "string",
            "description": "Layout name, shown in the QGIS layout manager",
            "required": True,
        },
        {
            "name": "page",
            "type": "string",
            "enum": sorted(PAGE_SIZES_MM),
            "description": f"Page size (default {DEFAULT_PAGE})",
            "required": False,
        },
        {
            "name": "orientation",
            "type": "string",
            "enum": list(ORIENTATIONS),
            "description": f"Page orientation (default {DEFAULT_ORIENTATION})",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        name = (params.get("name") or "").strip()
        if not name:
            raise ValueError("The layout needs a name.")
        if name in layout_names():
            raise ValueError(f"A layout named '{name}' already exists. Pick another name.")
        page_size_mm(params.get("page") or "", params.get("orientation") or "")
        prepared = dict(params)
        prepared["name"] = name
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = (params.get("name") or "").strip()
        page = (params.get("page") or DEFAULT_PAGE).strip().lower()
        return tr("Creating layout '{0}' ({1}).").format(name, page)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = (params.get("name") or "").strip()
        width, height = page_size_mm(params.get("page") or "", params.get("orientation") or "")
        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(name)
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, MM))
        project.layoutManager().addLayout(layout)
        return {"name": name, "page_mm": [width, height]}
