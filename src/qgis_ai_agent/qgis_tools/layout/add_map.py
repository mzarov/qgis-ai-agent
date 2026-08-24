from typing import Any

from qgis.core import QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize

from qgis_ai_agent.qgis_tools.base import BaseTool
from qgis_ai_agent.qgis_tools.layout.layout_composer import compose_map_box
from qgis_ai_agent.qgis_tools.layout.utils import (
    LAYOUT_UNIT_MM,
    get_layout,
    get_map_extent,
)


class AddMapTool(BaseTool):
    """Добавление элемента карты на макет (отображает текущий extent канваса/слоёв)."""
    name = "add_map"
    description = "Добавить рамку карты на макет. Позиция и размер в мм."
    capabilities = ["layout:map:add"]
    examples = ["Добавь карту в макет по центру"]
    constraints = ["layout_name должен существовать"]
    params_schema = [
        {"name": "layout_name", "type": "string", "description": "Имя макета", "required": True},
        {"name": "x", "type": "number", "description": "X левого верхнего угла в мм", "required": False},
        {"name": "y", "type": "number", "description": "Y левого верхнего угла в мм", "required": False},
        {"name": "width", "type": "number", "description": "Ширина рамки карты в мм", "required": False},
        {"name": "height", "type": "number", "description": "Высота рамки карты в мм", "required": False},
    ]

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = params.get("layout_name") or "Макет ИИ"
        layout = get_layout(layout_name)
        x = self._value_or_default(params.get("x"), None)
        y = self._value_or_default(params.get("y"), None)
        width = self._value_or_default(params.get("width"), None)
        height = self._value_or_default(params.get("height"), None)
        box = compose_map_box(layout, x=x, y=y, width=width, height=height)

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(box["x"], box["y"], LAYOUT_UNIT_MM))
        map_item.attemptResize(QgsLayoutSize(box["width"], box["height"], LAYOUT_UNIT_MM))
        map_item.zoomToExtent(get_map_extent())
        layout.addLayoutItem(map_item)
        return {"layout_name": layout_name}

    @staticmethod
    def _value_or_default(raw_value: Any, default: float | None) -> float | None:
        if raw_value is None:
            return default
        return float(raw_value)
