from typing import Any

from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.values import plain_value
from qgis_ai_agent.qgis_tools.common.colors import parse_color
from qgis_ai_agent.qgis_tools.style.apply import (
    coloured_symbol,
    refresh,
    require_field,
    require_vector_layer,
    resolve_ramp,
)

MAX_CATEGORIES = 60
DEFAULT_RAMPS = ("Set2", "Spectral", "Paired", "Viridis")


class SetCategoriesTool(BaseTool):
    name = "set_categories"
    description = (
        "Colour a layer by categories: every value of a field gets its own colour. "
        "Colours come from a QGIS ramp or from a list. Replaces the styling of the layer."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "The field must exist in the layer",
        "Either a ramp or a list of colours — one of the two",
    ]
    examples = ["Colour the roads by type", "Cities by region, Set2 ramp"]
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
            "description": "Field whose values split the features into categories",
            "required": True,
        },
        {
            "name": "ramp",
            "type": "string",
            "description": (
                "Name of a QGIS colour ramp, for example Spectral or Set2. Without it a "
                "sensible default is used; an unknown name comes back with the available list."
            ),
            "required": False,
        },
        {
            "name": "colors",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Colours, one per category, in the order of the values. Use it when "
                "specific colours are wanted instead of a ramp."
            ),
            "required": False,
        },
        {
            "name": "values",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Which values of the field to show. By default every unique value in the layer."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = require_field(layer, (params.get("field") or "").strip())
        values = _wanted_values(layer, field, params.get("values"))
        if not values:
            raise ValueError(f"Field '{field}' of layer '{layer.name()}' holds no values to categorise.")
        if len(values) > MAX_CATEGORIES:
            raise ValueError(
                f"Field '{field}' has {len(values)} distinct values, which is over {MAX_CATEGORIES}. "
                "For numeric data use set_graduated, otherwise narrow the values list down."
            )
        colors = params.get("colors") or []
        if colors and len(colors) != len(values):
            raise ValueError(
                f"There are {len(colors)} colours and {len(values)} categories. Give one colour "
                "per category, or pass a ramp instead of a list."
            )
        for color in colors:
            parse_color(color, "Category colour")
        if not colors:
            resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS)
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["field"] = field
        prepared["values"] = values
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return tr("Colouring '{0}' by field '{1}'.").format(layer_name, params.get("field", ""))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = params.get("field") or ""
        values = params.get("values") or _wanted_values(layer, field, None)
        colors = _colours_for(values, params.get("colors"), params.get("ramp"))
        categories = [
            QgsRendererCategory(value, coloured_symbol(layer, colour), str(value))
            for value, colour in zip(values, colors)
        ]
        layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
        refresh(layer)
        return {
            "layer": layer.name(),
            "renderer": "categorizedSymbol",
            "class_attribute": field,
            "class_count": len(categories),
        }


def _wanted_values(layer: Any, field: str, requested: Any) -> list[Any]:
    if requested:
        return list(requested)
    index = layer.fields().indexFromName(field)
    if index < 0:
        return []
    return sorted(
        (plain_value(value) for value in layer.uniqueValues(index)),
        key=lambda item: (item is None, str(item)),
    )


def _colours_for(values: list[Any], colors: Any, ramp_name: Any) -> list[Any]:
    if colors:
        return [parse_color(colour, "Category colour") for colour in colors]
    ramp = resolve_ramp(ramp_name or "", DEFAULT_RAMPS)
    total = max(1, len(values) - 1)
    return [ramp.color(index / total) for index in range(len(values))]
