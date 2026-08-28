from typing import Any

from qgis.core import QgsRasterLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name
from qgis_ai_agent.qgis_tools.style.apply import refresh
from qgis_ai_agent.qgis_tools.style.raster import (
    DEFAULT_CLASSES,
    INTERPOLATION,
    MAX_CLASSES,
    MIN_CLASSES,
    MODE_GRAY,
    MODE_HILLSHADE,
    MODE_PSEUDOCOLOR,
    MODES,
    apply_no_data,
    build_gray,
    build_hillshade,
    build_pseudocolor,
    checked_band,
    checked_classes,
    checked_interpolation,
)


class SetRasterStyleTool(BaseTool):
    name = "set_raster_style"
    description = (
        "Style a raster layer: a colour ramp over the values (pseudocolor), "
        "grayscale, or a shaded relief from elevation (hillshade). Also hides "
        "no-data values. Replaces the raster renderer."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "The layer must exist and be a raster layer",
        "The band must exist in the raster",
    ]
    examples = [
        "Colour the elevation model with Viridis",
        "Make a hillshade from the DEM",
        "Hide the -9999 values on the raster",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "mode",
            "type": "string",
            "enum": list(MODES),
            "description": (
                "pseudocolor paints values with a ramp, gray is a grayscale stretch, hillshade shades an elevation band"
            ),
            "required": True,
        },
        {
            "name": "band",
            "type": "integer",
            "description": "Which band to render, 1 by default",
            "required": False,
        },
        {
            "name": "ramp",
            "type": "string",
            "description": "Colour ramp name for pseudocolor, e.g. Viridis or Spectral",
            "required": False,
        },
        {
            "name": "classes",
            "type": "integer",
            "description": f"Colour classes for pseudocolor, {MIN_CLASSES}-{MAX_CLASSES} (default {DEFAULT_CLASSES})",
            "required": False,
        },
        {
            "name": "interpolation",
            "type": "string",
            "enum": sorted(INTERPOLATION),
            "description": "How colours change between classes; linear by default",
            "required": False,
        },
        {
            "name": "azimuth",
            "type": "number",
            "description": "Light direction for hillshade, degrees (default 315)",
            "required": False,
        },
        {
            "name": "altitude",
            "type": "number",
            "description": "Light height for hillshade, degrees (default 45)",
            "required": False,
        },
        {
            "name": "no_data_values",
            "type": "array",
            "items": {"type": "number"},
            "description": "Values to hide as transparent, e.g. [-9999]",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_raster(params.get("layer_name") or "")
        mode = _checked_mode(params.get("mode"))
        checked_band(layer, params.get("band"))
        if mode == MODE_PSEUDOCOLOR:
            checked_classes(params.get("classes"))
            checked_interpolation(params.get("interpolation"))
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["mode"] = mode
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        mode = str(params.get("mode") or "").strip()
        return tr("Styling raster '{0}': {1}.").format(layer_name, mode)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_raster(params.get("layer_name") or "")
        mode = _checked_mode(params.get("mode"))
        band = checked_band(layer, params.get("band"))
        hidden = apply_no_data(layer, params.get("no_data_values"))
        renderer, details = _built(layer, mode, band, params)
        layer.setRenderer(renderer)
        refresh(layer)
        result: dict[str, Any] = {"layer": layer.name(), "mode": mode, "band": band}
        result.update(details)
        if hidden:
            result["hidden_values"] = hidden
        return result


def _built(layer: Any, mode: str, band: int, params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    if mode == MODE_PSEUDOCOLOR:
        return build_pseudocolor(
            layer,
            band,
            str(params.get("ramp") or ""),
            checked_classes(params.get("classes")),
            checked_interpolation(params.get("interpolation")),
        )
    if mode == MODE_GRAY:
        return build_gray(layer, band)
    return build_hillshade(layer, band, params.get("azimuth"), params.get("altitude"))


def _require_raster(layer_name: str) -> QgsRasterLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsRasterLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a raster layer — use the vector styling tools instead.")
    return layer


def _checked_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode not in MODES:
        raise ValueError(f"Unknown raster mode '{raw}'. Available: {', '.join(MODES)}.")
    if mode == MODE_HILLSHADE:
        return MODE_HILLSHADE
    return mode
