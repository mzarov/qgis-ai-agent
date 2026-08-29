from typing import Any

from qgis.core import QgsSingleSymbolRenderer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import geometry_type_name
from ai_agent.qgis_tools.common.properties import properties_of, shown
from ai_agent.qgis_tools.style.apply import refresh, require_vector_layer
from ai_agent.qgis_tools.style.symbol_build import build_symbol, note_for
from ai_agent.qgis_tools.style.symbol_catalogue import SYMBOLS


class SetSymbolTool(BaseTool):
    name = "set_symbol"
    description = (
        "Style a layer with a single symbol: colour, opacity, point size or "
        "line width, stroke and its dash pattern, marker shape, fill hatching. "
        "describe_style_options returns the full list of properties. Replaces "
        "the current styling of the layer."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "The layer must exist and be a vector layer",
        "All properties go in one call, not several",
    ]
    examples = [
        "Make the rivers blue",
        "Roads as thin grey dashed lines",
        "Cities as square markers with a white stroke",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "properties",
            "type": "object",
            "description": (
                "Symbol properties as key-value pairs, for example "
                '{"color": "#1f78b4", "stroke_color": "white", "size": 2}. '
                "Names and allowed values come from describe_style_options "
                'with kind="symbol". An unknown key comes back with a hint.'
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = SYMBOLS.coerce_all(properties_of(params, SYMBOLS.subject))
        if not properties:
            raise ValueError(
                'No symbol property was given. describe_style_options with kind="symbol" lists the available ones.'
            )
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["properties"] = properties
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        try:
            properties = properties_of(params, SYMBOLS.subject)
        except ValueError:
            return tr("Styling layer '{0}'.").format(layer_name)
        return tr("Styling '{0}': {1}.").format(layer_name, shown(properties, SYMBOLS))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = SYMBOLS.coerce_all(properties_of(params, SYMBOLS.subject))
        symbol, outcome = build_symbol(layer, properties)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        refresh(layer)
        result: dict[str, Any] = {
            "layer": layer.name(),
            "renderer": "singleSymbol",
            "applied": outcome["applied"],
        }
        note = note_for(outcome["skipped"], geometry_type_name(layer))
        if note:
            result["skipped"] = outcome["skipped"]
            result["skipped_note"] = note
        return result
