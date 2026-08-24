from typing import Any

from qgis.core import (
    QgsLayoutItem,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
)

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.layout.utils import (
    get_layout,
    get_page_size_mm,
    item_bbox_mm,
    resolve_layout_zones,
)

# Человекочитаемые имена типов элементов макета.
_ITEM_KINDS = (
    (QgsLayoutItemMap, "map"),
    (QgsLayoutItemLegend, "legend"),
    (QgsLayoutItemScaleBar, "scalebar"),
    (QgsLayoutItemLabel, "label"),
)


class InspectLayoutTool(BaseTool):
    """Осмотр содержимого макета: элементы, их позиции и свободные зоны."""
    name = "inspect_layout"
    description = (
        "Показать содержимое макета: список элементов (карта, легенда, линейка, надписи) "
        "с позицией и размером в мм, размер страницы и рабочие зоны. "
        "Нужен перед правкой существующего макета."
    )
    skill = "inspect"
    safety = SAFETY_READ
    capabilities = ["layout:inspect"]
    examples = ["Что уже есть на макете «Карта района»?", "Проверь, есть ли там легенда"]
    constraints = ["Макет с указанным именем должен существовать"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Имя макета ровно как в проекте (см. list_layouts)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага осмотра макета."""
        layout_name = (params.get("layout_name") or "").strip()
        return f"Смотрю макет «{layout_name}»." if layout_name else "Смотрю макет."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = (params.get("layout_name") or "").strip()
        layout = get_layout(layout_name)
        page_width, page_height = get_page_size_mm(layout)
        zones = resolve_layout_zones(layout)
        return {
            "name": layout.name(),
            "page_width_mm": round(page_width, 1),
            "page_height_mm": round(page_height, 1),
            "orientation": "landscape" if page_width > page_height else "portrait",
            "items": self._describe_items(layout),
            "zones": self._describe_zones(zones),
        }

    @classmethod
    def _describe_items(cls, layout) -> list[dict[str, Any]]:
        """Собирает элементы макета с типом, позицией и размером."""
        items: list[dict[str, Any]] = []
        for item in layout.items():
            if not isinstance(item, QgsLayoutItem):
                continue
            bbox = item_bbox_mm(item)
            if not bbox:
                continue
            x, y, width, height = bbox
            entry: dict[str, Any] = {
                "kind": cls._item_kind(item),
                "x": round(x, 1),
                "y": round(y, 1),
                "width": round(width, 1),
                "height": round(height, 1),
            }
            if isinstance(item, QgsLayoutItemLabel):
                entry["text"] = (item.text() or "").strip()
            items.append(entry)
        return items

    @staticmethod
    def _item_kind(item: QgsLayoutItem) -> str:
        for item_class, kind in _ITEM_KINDS:
            if isinstance(item, item_class):
                return kind
        return "other"

    @staticmethod
    def _describe_zones(zones: dict[str, float]) -> dict[str, Any]:
        """Отдаёт только зоны размещения, без служебных полей policy."""
        return {
            "top_band": {
                "x": round(zones["top_band_x"], 1),
                "y": round(zones["top_band_y"], 1),
                "width": round(zones["top_band_w"], 1),
                "height": round(zones["top_band_h"], 1),
            },
            "content": {
                "x": round(zones["content_x"], 1),
                "y": round(zones["content_y"], 1),
                "width": round(zones["content_w"], 1),
                "height": round(zones["content_h"], 1),
            },
            "legend": {
                "x": round(zones["legend_x"], 1),
                "y": round(zones["legend_y"], 1),
                "width": round(zones["legend_w"], 1),
                "height": round(zones["legend_h"], 1),
            },
            "footer": {
                "x": round(zones["footer_x"], 1),
                "y": round(zones["footer_y"], 1),
                "width": round(zones["footer_w"], 1),
                "height": round(zones["footer_h"], 1),
            },
        }
