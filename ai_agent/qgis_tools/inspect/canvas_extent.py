from typing import Any

from qgis.core import QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layers import canvas_extent, extent_dict


class GetCanvasExtentTool(BaseTool):
    name = "get_canvas_extent"
    description = "Show the current extent of the QGIS canvas and the project coordinate system."
    skill = "inspect"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    examples = ["What is the current map extent?", "What is visible on screen right now?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the current map extent.")

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
