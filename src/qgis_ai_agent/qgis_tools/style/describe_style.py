from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layer_meta import layer_opacity
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name, layer_kind
from qgis_ai_agent.qgis_tools.style.labeling import describe_labeling
from qgis_ai_agent.qgis_tools.style.renderers import (
    describe_raster_renderer,
    describe_vector_renderer,
)


class DescribeStyleTool(BaseTool):
    name = "describe_style"
    description = (
        "Показать оформление слоя: тип рендерера, поле классификации, классы "
        "со значениями и цветами, подписи и прозрачность."
    )
    skill = "style"
    safety = SAFETY_READ
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    examples = ["Почему города красные?", "Как сейчас раскрашен слой дорог?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте (см. list_layers)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Смотрю оформление слоя «{layer_name}»." if layer_name else "Смотрю оформление слоя."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        result: dict[str, Any] = {
            "name": (layer.name() or "").strip(),
            "kind": layer_kind(layer),
            "opacity": layer_opacity(layer),
        }
        if isinstance(layer, QgsVectorLayer):
            result["renderer"] = describe_vector_renderer(layer)
            result["labeling"] = describe_labeling(layer)
        elif isinstance(layer, QgsRasterLayer):
            result["renderer"] = describe_raster_renderer(layer)
        return result
