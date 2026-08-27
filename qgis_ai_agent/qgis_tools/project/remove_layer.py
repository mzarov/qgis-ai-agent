from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.project.tree import find_layer, project


class RemoveLayerTool(BaseTool):
    name = "remove_layer"
    description = (
        "Убрать слой из проекта. Файл на диске не трогается — удаляется только "
        "слой из проекта вместе с его оформлением."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    examples = ["Убери слой временного буфера", "Удали лишний слой из проекта"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Убираю слой «{layer_name}» из проекта."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        name = layer.name()
        project().removeMapLayer(layer.id())
        return {"removed": name, "note": "Файл на диске остался на месте."}
