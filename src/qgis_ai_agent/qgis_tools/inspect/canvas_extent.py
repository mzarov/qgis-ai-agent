from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.utils import extent_dict
from qgis_ai_agent.qgis_tools.layout.utils import get_map_extent


class GetCanvasExtentTool(BaseTool):
    """Текущий охват карты — то, что попадёт в рамку карты макета."""
    name = "get_canvas_extent"
    description = (
        "Показать текущий охват (extent) канваса QGIS и систему координат проекта. "
        "Это тот охват, который получит рамка карты при добавлении на макет."
    )
    skill = "inspect"
    safety = SAFETY_READ
    capabilities = ["project:canvas:extent"]
    examples = ["Какой сейчас охват карты?", "Что попадёт в макет?"]
    constraints = []
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага чтения охвата канваса."""
        return "Смотрю текущий охват карты."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        extent = extent_dict(get_map_extent())
        crs = ""
        try:
            crs = QgsProject.instance().crs().authid() or ""
        except Exception:
            pass
        return {"extent": extent, "project_crs": crs}
