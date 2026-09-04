from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layer_meta import layer_opacity
from ai_agent.qgis_tools.common.layers import find_layer_by_name, layer_kind
from ai_agent.qgis_tools.style.labeling import describe_labeling
from ai_agent.qgis_tools.style.renderers import (
    describe_raster_renderer,
    describe_vector_renderer,
)


class DescribeStyleTool(BaseTool):
    name = "describe_style"
    description = (
        "Show the styling of a layer: renderer type, classification field, classes "
        "with their values and colours, labels and opacity."
    )
    skill = "style"
    safety = SAFETY_READ
    external_effect = False
    network_access = False
    egress = EGRESS_FEATURE_VALUES
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Why are the cities red?", "How is the roads layer coloured right now?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project (see list_layers)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not layer_name:
            return tr("Reading the layer styling.")
        return tr("Reading the styling of layer '{0}'.").format(layer_name)

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
