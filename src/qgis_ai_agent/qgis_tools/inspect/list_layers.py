from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.utils import describe_layer_brief


class ListLayersTool(BaseTool):
    """Перечисление слоёв проекта с типом, геометрией и системой координат."""
    name = "list_layers"
    description = (
        "Показать слои текущего проекта QGIS: имя, вид (вектор/растр), "
        "тип геометрии, систему координат и число объектов."
    )
    skill = "inspect"
    safety = SAFETY_READ
    capabilities = ["project:layers:list"]
    examples = ["Что за слои у меня в проекте?", "Какие данные загружены?"]
    constraints = []
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага чтения списка слоёв."""
        return "Смотрю слои проекта."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        project = QgsProject.instance()
        layers = [describe_layer_brief(layer) for layer in project.mapLayers().values()]
        return {"layers": layers, "count": len(layers)}
