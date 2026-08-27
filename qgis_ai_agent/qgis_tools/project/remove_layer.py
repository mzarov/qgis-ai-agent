from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.project.tree import find_layer, project


class RemoveLayerTool(BaseTool):
    name = "remove_layer"
    description = (
        "Remove a layer from the project. The file on disk is left alone — only the "
        "layer and its styling go away."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Drop the temporary buffer layer", "Remove the spare layer from the project"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
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
        return tr("Removing layer '{0}' from the project.").format(layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        name = layer.name()
        project().removeMapLayer(layer.id())
        return {"removed": name, "note": "The file on disk stayed where it was."}
