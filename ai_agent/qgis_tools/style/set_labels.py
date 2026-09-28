from typing import Any

from qgis.core import QgsVectorLayerSimpleLabeling

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import layer_reference
from ai_agent.qgis_tools.common.properties import as_bool, properties_of, shown
from ai_agent.qgis_tools.common.values import suggest_fields
from ai_agent.qgis_tools.style.apply import (
    field_names,
    refresh,
    require_field,
    require_vector_layer,
)
from ai_agent.qgis_tools.style.label_build import addresses, build_settings, current_simple_settings, wants
from ai_agent.qgis_tools.style.label_catalogue import LABELS, TARGET_BUFFER

FIELD_NEEDED = "The labels are off, so switching them on needs the field property. {hint}"


class SetLabelsTool(BaseTool):
    name = "set_labels"
    description = (
        "Configure the labels of a layer in one call: field, font, weight, size, "
        "colour, text buffer, offset, rotation, placement, shadow, background. "
        "describe_style_options returns the full list of properties. When labels "
        "are already on, only the given properties change; the rest of the "
        "labeling and of the layer styling is left alone."
    )
    skill = "style"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "The label field must exist in the layer",
        "field is required only when the labels are currently off",
        "All properties go in one call, not several",
    ]
    examples = [
        "Label the cities with their names",
        "Make the labels bold with a white buffer",
        "Move the labels 3 mm up",
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
                "Label properties as key-value pairs, for example "
                '{"field": "name", "bold": true, "buffer_color": "white", '
                '"offset_y": -3}. Names and allowed values come from '
                'describe_style_options with kind="labels". An unknown key comes back with a hint.'
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = LABELS.coerce_all(properties_of(params, LABELS.subject))
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["properties"] = properties
        if not _is_enabled(properties):
            return prepared
        field = str(properties.get("field") or "").strip()
        if field:
            properties["field"] = require_field(layer, field)
        elif current_simple_settings(layer) is None:
            raise ValueError(FIELD_NEEDED.format(hint=suggest_fields([], field_names(layer))))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        try:
            properties = properties_of(params, LABELS.subject)
        except ValueError:
            return tr("Setting up labels for '{0}'.").format(layer_name)
        if not _is_enabled(properties):
            return tr("Removing the labels from layer '{0}'.").format(layer_name)
        return tr("Setting up labels for '{0}': {1}.").format(layer_name, shown(properties, LABELS))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = LABELS.coerce_all(properties_of(params, LABELS.subject))
        if not _is_enabled(properties):
            layer.setLabelsEnabled(False)
            refresh(layer)
            return {**layer_reference(layer), "labels": False}

        base = current_simple_settings(layer)
        if base is None and not str(properties.get("field") or "").strip():
            raise ValueError(FIELD_NEEDED.format(hint=suggest_fields([], field_names(layer))))
        settings = build_settings(properties, base)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        refresh(layer)
        result = {
            **layer_reference(layer),
            "labels": True,
            "kept_existing": base is not None,
            "field": settings.fieldName,
            "applied": sorted(key for key in properties if key != "enabled"),
        }
        if base is None or addresses(properties, TARGET_BUFFER):
            result["buffer"] = wants(properties, TARGET_BUFFER)
        return result


def _is_enabled(properties: dict[str, Any]) -> bool:
    value = properties.get("enabled")
    return True if value is None else as_bool(value)
