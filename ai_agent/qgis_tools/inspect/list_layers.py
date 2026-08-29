from typing import Any

from qgis.core import QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layers import describe_layer_brief


class ListLayersTool(BaseTool):
    name = "list_layers"
    description = (
        "List the layers of the current QGIS project: name, kind (vector/raster), "
        "geometry type, coordinate system and feature count."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["What layers does my project have?", "Which data is loaded?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the project layers.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layers = [describe_layer_brief(layer) for layer in QgsProject.instance().mapLayers().values()]
        return {"layers": layers, "count": len(layers)}
