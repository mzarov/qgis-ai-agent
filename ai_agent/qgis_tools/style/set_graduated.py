from typing import Any

from qgis.core import QgsGraduatedSymbolRenderer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.style.apply import (
    base_symbol,
    refresh,
    require_field,
    require_vector_layer,
    resolve_ramp,
)

MODES = {
    "equal": "EqualInterval",
    "quantile": "Quantile",
    "jenks": "Jenks",
    "pretty": "Pretty",
    "stddev": "StdDev",
}
DEFAULT_MODE = "quantile"
DEFAULT_CLASSES = 5
MIN_CLASSES = 2
MAX_CLASSES = 20
DEFAULT_RAMPS = ("Viridis", "Blues", "Spectral")


class SetGraduatedTool(BaseTool):
    name = "set_graduated"
    description = (
        "Colour a layer with graduated classes over a numeric field: split the values "
        "into classes and fill them from a ramp. Replaces the styling of the layer."
    )
    skill = "style"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "The field must exist and hold numbers",
        f"The number of classes runs from {MIN_CLASSES} to {MAX_CLASSES}",
    ]
    examples = ["Colour the districts by population", "Graduate by area, 7 classes, Viridis"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "field",
            "type": "string",
            "description": "Numeric field the graduation is built on",
            "required": True,
        },
        {
            "name": "ramp",
            "type": "string",
            "description": (
                "Name of a QGIS colour ramp, for example Viridis or Reds. Without it a "
                "sensible default is used; an unknown name comes back with the available list."
            ),
            "required": False,
        },
        {
            "name": "classes",
            "type": "integer",
            "description": f"How many classes, {DEFAULT_CLASSES} by default",
            "required": False,
        },
        {
            "name": "mode",
            "type": "string",
            "enum": sorted(MODES),
            "description": (
                "How to split: quantile for an equal number of features per class, equal "
                "for equal intervals, jenks for natural breaks, pretty for round numbers, "
                "stddev for standard deviation."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = require_field(layer, (params.get("field") or "").strip())
        _require_numeric(layer, field)
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["field"] = field
        prepared["classes"] = _class_count(params.get("classes"))
        prepared["mode"] = _mode_name(params.get("mode"))
        resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        classes = params.get("classes") or DEFAULT_CLASSES
        return tr("Graduating '{0}' by '{1}', classes: {2}.").format(layer_name, params.get("field", ""), classes)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = params.get("field") or ""
        classes = _class_count(params.get("classes"))
        mode = _mode_name(params.get("mode"))
        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            field,
            classes,
            getattr(QgsGraduatedSymbolRenderer, MODES[mode]),
            base_symbol(layer),
            resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS),
        )
        if renderer is None:
            raise ValueError(
                f"QGIS could not build graduated classes on field '{field}': the values may all be equal or empty."
            )
        layer.setRenderer(renderer)
        refresh(layer)
        return {
            "layer": layer.name(),
            "renderer": "graduatedSymbol",
            "class_attribute": field,
            "class_count": len(renderer.ranges()),
            "mode": mode,
        }


def _require_numeric(layer: Any, field: str) -> None:
    index = layer.fields().indexFromName(field)
    if index < 0:
        return
    if not layer.fields().at(index).isNumeric():
        raise ValueError(
            f"Field '{field}' is not numeric, so graduated classes cannot be built on it. "
            "For text values use set_categories."
        )


def _class_count(value: Any) -> int:
    if value is None:
        return DEFAULT_CLASSES
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"The number of classes is a whole number from {MIN_CLASSES} to {MAX_CLASSES}.") from None
    if number < MIN_CLASSES or number > MAX_CLASSES:
        raise ValueError(f"The number of classes must run from {MIN_CLASSES} to {MAX_CLASSES}.")
    return number


def _mode_name(value: Any) -> str:
    name = (str(value or DEFAULT_MODE)).strip().lower()
    if name not in MODES:
        raise ValueError(f"Unknown split mode '{value}'. Available: {', '.join(sorted(MODES))}.")
    return name
