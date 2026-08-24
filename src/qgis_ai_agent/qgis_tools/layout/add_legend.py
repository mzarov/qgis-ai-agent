from typing import Any

from qgis.core import QgsLayoutItemLegend, QgsLayoutPoint, QgsLayoutSize

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.layout.layout_composer import compose_legend_box
from qgis_ai_agent.qgis_tools.layout.utils import (
    LAYOUT_UNIT_MM,
    get_first_map_item,
    get_layout,
)


class AddLegendTool(BaseTool):
    """Добавление легенды на макет, привязанной к карте."""
    name = "add_legend"
    description = "Добавить легенду слоёв. Привязывается к первой карте в макете. Координаты в мм."
    skill = "layout"
    safety = SAFETY_WRITE
    capabilities = ["layout:legend:add"]
    examples = ["Добавь легенду справа от карты"]
    constraints = ["Для корректной привязки в макете желательно наличие карты"]
    params_schema = [
        {"name": "layout_name", "type": "string", "description": "Имя макета", "required": True},
        {"name": "x", "type": "number", "description": "X левого верхнего угла легенды в мм", "required": False},
        {"name": "y", "type": "number", "description": "Y левого верхнего угла легенды в мм", "required": False},
        {"name": "title", "type": "string", "description": "Заголовок легенды", "required": False},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага добавления легенды для чата."""
        x, y = params.get("x"), params.get("y")
        title = (params.get("title") or "").strip()
        where = f" в ({x}, {y}) мм" if x is not None and y is not None else ""
        titled = f", заголовок «{title}»" if title else ""
        return f"Добавить легенду{where}{titled}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = params.get("layout_name") or "Макет ИИ"
        title = params.get("title")

        layout = get_layout(layout_name)
        map_item = get_first_map_item(layout)
        box = compose_legend_box(
            layout=layout,
            x=float(params.get("x")) if params.get("x") is not None else None,
            y=float(params.get("y")) if params.get("y") is not None else None,
            width=None,
            height=None,
        )

        legend = QgsLayoutItemLegend(layout)
        legend.attemptMove(QgsLayoutPoint(box["x"], box["y"], LAYOUT_UNIT_MM))
        legend.attemptResize(QgsLayoutSize(box["width"], box["height"], LAYOUT_UNIT_MM))
        legend.setAutoUpdateModel(True)
        if map_item:
            legend.setLinkedMap(map_item)
        if title is not None:
            legend.setTitle(title)
        else:
            legend.setTitle("")
        layout.addLayoutItem(legend)
        return {"layout_name": layout_name}
