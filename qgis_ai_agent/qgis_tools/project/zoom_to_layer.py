from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import extent_dict, safe_extent
from qgis_ai_agent.qgis_tools.project.tree import find_layer


class ZoomToLayerTool(BaseTool):
    name = "zoom_to_layer"
    description = (
        "Показать слой целиком на карте: подогнать вид под его охват. "
        "Меняет только вид, ни проект, ни данные не трогает."
    )
    skill = "project"
    safety = SAFETY_READ
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    examples = ["Покажи слой городов", "Приблизь к дорогам"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Показываю слой «{layer_name}» целиком." if layer_name else "Подгоняю вид карты."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        extent = safe_extent(layer)
        if extent is None:
            raise ValueError(f"У слоя «{layer.name()}» нет охвата — возможно, он пуст.")
        if not _apply_extent(layer, extent):
            raise ValueError("Карта недоступна: плагин запущен без окна QGIS.")
        return {"layer": layer.name(), "extent": extent_dict(extent)}


def _apply_extent(layer: Any, extent: Any) -> bool:
    try:
        from qgis.utils import iface

        canvas = iface.mapCanvas()
    except Exception:
        return False
    try:
        canvas.setExtent(canvas.mapSettings().layerExtentToOutputExtent(layer, extent))
        canvas.refresh()
    except Exception:
        return False
    return True
