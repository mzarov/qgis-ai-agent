from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.utils import describe_layer_brief


class ListLayersTool(BaseTool):
    name = "list_layers"
    description = (
        "Показать слои текущего проекта QGIS: имя, вид (вектор/растр), "
        "тип геометрии, систему координат и число объектов."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["Что за слои у меня в проекте?", "Какие данные загружены?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return "Смотрю слои проекта."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layers = [
            describe_layer_brief(layer)
            for layer in QgsProject.instance().mapLayers().values()
        ]
        return {"layers": layers, "count": len(layers)}
