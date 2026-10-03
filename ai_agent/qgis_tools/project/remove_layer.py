from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.project.scratch_copies import is_memory_layer, scratch_layers_over_budget
from ai_agent.qgis_tools.project.tree import find_layer, project


class RemoveLayerTool(BaseTool):
    name = "remove_layer"
    description = (
        "Remove a layer from the project. The file on disk is left alone — only the layer and its styling go away."
    )
    skill = "project"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Drop the temporary buffer layer", "Remove the spare layer from the project"]
    params_schema = [
        params.layer_name(),
    ]

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        """A scratch layer too large to copy beside the snapshot is gone for good once removed."""
        try:
            layer = find_layer(params.get("layer_name") or "")
        except Exception:
            return False
        return is_memory_layer(layer) and str(layer.id()) in scratch_layers_over_budget(project())

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
        scratch = is_memory_layer(layer)
        project().removeMapLayer(layer.id())
        if scratch:
            return {"removed": name, "note": "This was a temporary (memory) layer; its features lived only in QGIS."}
        return {"removed": name, "note": "The file on disk stayed where it was."}
