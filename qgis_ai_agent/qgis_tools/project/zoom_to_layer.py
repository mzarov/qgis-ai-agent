from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import extent_dict, safe_extent
from qgis_ai_agent.qgis_tools.project.tree import find_layer


class ZoomToLayerTool(BaseTool):
    name = "zoom_to_layer"
    description = (
        "Show a whole layer on the map: fit the view to its extent. "
        "Changes the view only, touches neither the project nor the data."
    )
    skill = "project"
    safety = SAFETY_READ
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Show me the cities layer", "Zoom to the roads"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not layer_name:
            return tr("Fitting the map view.")
        return tr("Showing the whole of layer '{0}'.").format(layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        extent = safe_extent(layer)
        if extent is None:
            raise ValueError(f"Layer '{layer.name()}' has no extent — it may be empty.")
        if not _apply_extent(layer, extent):
            raise ValueError("The map is not available: the plugin is running without a QGIS window.")
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
