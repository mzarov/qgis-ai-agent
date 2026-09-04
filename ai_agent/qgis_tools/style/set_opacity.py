from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.style.apply import refresh

PERCENT_THRESHOLD = 1.0
PERCENT_MAX = 100.0
MIN_OPACITY = 0.0
MAX_OPACITY = 1.0


class SetOpacityTool(BaseTool):
    name = "set_opacity"
    description = (
        "Set the opacity of a layer. Works for vector and raster layers alike, "
        "and leaves the rest of the styling alone."
    )
    skill = "style"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Make the basemap half transparent", "Give the layer back its full opacity"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "opacity",
            "type": "number",
            "description": ("Opacity from 0 to 1, where 1 is fully opaque. Values above 1 are read as percentages."),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["opacity"] = _as_fraction(params.get("opacity"))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip() or tr("the layer")
        try:
            percent = f"{_as_fraction(params.get('opacity')) * PERCENT_MAX:.0f}%"
        except ValueError:
            percent = tr("the given amount")
        return tr("Setting opacity of '{0}' to {1}.").format(layer_name, percent)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        opacity = _as_fraction(params.get("opacity"))
        layer.setOpacity(opacity)
        refresh(layer)
        return {"layer": layer.name(), "opacity": opacity}


def _as_fraction(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Opacity is given as a number from 0 to 1, for example 0.6.") from None
    if number > PERCENT_THRESHOLD:
        number = number / PERCENT_MAX
    return max(MIN_OPACITY, min(MAX_OPACITY, number))
