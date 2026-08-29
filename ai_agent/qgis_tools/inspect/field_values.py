from typing import Any

from qgis.core import QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.common.values import clamp_limit, plain_value, suggest_fields

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
NUMERIC_TYPES = ("int", "double", "real", "float", "numeric", "long", "short")


class GetFieldValuesTool(BaseTool):
    name = "get_field_values"
    description = (
        "Show what an attribute field contains: unique values and, for numeric "
        "fields, the minimum and the maximum. Needed before classifying, filtering "
        "or styling by that field."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["The layer and the field must exist", "The layer must be a vector layer"]
    examples = ["Which values does the type field hold?", "What is the range of city population?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "field_name",
            "type": "string",
            "description": "Field name exactly as in describe_layer",
            "required": True,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"How many unique values to return (default {DEFAULT_LIMIT})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        field_name = (params.get("field_name") or "").strip()
        return tr("Reading values of field '{0}' in layer '{1}'.").format(field_name, layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        if not isinstance(layer, QgsVectorLayer):
            raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no attribute fields.")
        field_name = (params.get("field_name") or "").strip()
        index = self._field_index(layer, field_name)
        limit = clamp_limit(params.get("limit"), DEFAULT_LIMIT, MAX_LIMIT)

        result: dict[str, Any] = {
            "layer_name": layer.name(),
            "field_name": field_name,
            "field_type": self._field_type(layer, index),
        }
        result.update(self._unique_values(layer, index, limit))
        if self._is_numeric(result["field_type"]):
            result.update(self._numeric_range(layer, index))
        return result

    @staticmethod
    def _field_index(layer: QgsVectorLayer, field_name: str) -> int:
        index = layer.fields().indexOf(field_name)
        if index < 0:
            hint = suggest_fields([field_name], layer.fields().names())
            raise ValueError(f"Field not found: '{field_name}'. {hint}")
        return index

    @staticmethod
    def _field_type(layer: QgsVectorLayer, index: int) -> str:
        try:
            field = layer.fields().at(index)
            return field.typeName() or str(field.type())
        except Exception:
            return ""

    @staticmethod
    def _unique_values(layer: QgsVectorLayer, index: int, limit: int) -> dict[str, Any]:
        try:
            values = layer.uniqueValues(index, limit + 1)
        except Exception:
            return {"unique_values": [], "unique_values_note": "the values are not available"}
        plain = [plain_value(value) for value in values]
        filled = _sorted_safe([value for value in plain if value is not None])

        result: dict[str, Any] = {"unique_values": filled[:limit]}
        if len(filled) > limit:
            result["unique_values_note"] = f"showing the first {limit}, there are more values"
        else:
            result["unique_values_count"] = len(filled)
        if len(plain) != len(filled):
            result["has_null_values"] = True
            result["null_note"] = "the field has empty values, they are not included in the list"
        return result

    @staticmethod
    def _is_numeric(field_type: str) -> bool:
        lowered = (field_type or "").lower()
        return any(marker in lowered for marker in NUMERIC_TYPES)

    @staticmethod
    def _numeric_range(layer: QgsVectorLayer, index: int) -> dict[str, Any]:
        info: dict[str, Any] = {}
        for key, getter in (("min", "minimumValue"), ("max", "maximumValue")):
            try:
                info[key] = plain_value(getattr(layer, getter)(index))
            except Exception:
                continue
        return info


def _sorted_safe(values: list[Any]) -> list[Any]:
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=lambda value: (type(value).__name__, str(value)))
