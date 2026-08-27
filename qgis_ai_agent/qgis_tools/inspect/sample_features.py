from typing import Any

from qgis.core import QgsFeatureRequest, QgsVectorLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name, safe_feature_count
from qgis_ai_agent.qgis_tools.common.values import clamp_limit, plain_value, wanted_fields

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_VALUE_CHARS = 120


class SampleFeaturesTool(BaseTool):
    name = "sample_features"
    description = (
        "Show a few real records of a layer together with their attribute values. "
        "Needed when the field schema is not enough and you have to see the actual data."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["The layer must exist and be a vector layer"]
    examples = ["Show me a couple of records from the cities layer", "What does the data look like?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"How many records to return (default {DEFAULT_LIMIT})",
            "required": False,
        },
        {
            "name": "fields",
            "type": "array",
            "items": {"type": "string"},
            "description": "Which fields to show. All of them by default.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return tr("Reading records of layer '{0}'.").format(layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        if not isinstance(layer, QgsVectorLayer):
            raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no records.")
        limit = clamp_limit(params.get("limit"), DEFAULT_LIMIT, MAX_LIMIT)
        wanted = wanted_fields(layer, params.get("fields"))

        features = []
        for feature in layer.getFeatures(QgsFeatureRequest().setLimit(limit)):
            features.append(self._describe_feature(feature, wanted))
        return {
            "layer_name": layer.name(),
            "shown": len(features),
            "total": safe_feature_count(layer),
            "features": features,
        }

    @staticmethod
    def _describe_feature(feature, wanted: list[str] | None) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        try:
            names = feature.fields().names()
        except Exception:
            names = []
        for name in names:
            if wanted is not None and name not in wanted:
                continue
            attributes[name] = _truncated(plain_value(feature[name]))
        entry: dict[str, Any] = {"attributes": attributes}
        geometry_type = _geometry_type(feature)
        if geometry_type:
            entry["geometry"] = geometry_type
        return entry


def _geometry_type(feature) -> str:
    try:
        geometry = feature.geometry()
        if geometry.isEmpty():
            return "empty"
        return str(geometry.type()).split(".")[-1]
    except Exception:
        return ""


def _truncated(value: Any) -> Any:
    if not isinstance(value, str) or len(value) <= MAX_VALUE_CHARS:
        return value
    return value[:MAX_VALUE_CHARS] + "…"
