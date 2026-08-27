from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import canvas_extent, extent_dict


class GetCanvasExtentTool(BaseTool):
    name = "get_canvas_extent"
    description = (
        "Показать текущий охват (extent) канваса QGIS и систему координат проекта."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["Какой сейчас охват карты?", "Что сейчас видно на экране?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return "Смотрю текущий охват карты."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "extent": extent_dict(canvas_extent()),
            "project_crs": self._project_crs(),
        }

    @staticmethod
    def _project_crs() -> str:
        try:
            return QgsProject.instance().crs().authid() or ""
        except Exception:
            return ""
