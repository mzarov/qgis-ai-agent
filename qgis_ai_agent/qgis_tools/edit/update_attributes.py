from typing import Any

from qgis.core import QgsVectorLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, BaseTool
from qgis_ai_agent.qgis_tools.common.expressions import build_context, build_request
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name
from qgis_ai_agent.qgis_tools.common.values import suggest_fields

MAX_SCAN = 50000
COMMIT_FAILED = "QGIS could not commit the attribute edits: {reason}. The layer was rolled back and nothing changed."


class UpdateAttributesTool(BaseTool):
    name = "update_attributes"
    description = (
        "Change attribute values of existing features in place: set the listed "
        "fields to new constant values on every feature matching the filter. "
        "This edits the underlying data — for computed values use "
        "native:fieldcalculator instead."
    )
    skill = "edit"
    safety = SAFETY_DESTRUCTIVE
    constraints = [
        "The layer must be an editable vector layer",
        "The fields must exist; values are constants, not expressions",
        "Without a filter every feature is touched — pass one whenever possible",
    ]
    examples = ["Set type to 'park' for the selected polygons", "Fix the misspelled city name"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "values",
            "type": "object",
            "description": 'New values per field, e.g. {"type": "park", "verified": 1}',
            "required": True,
        },
        {
            "name": "filter",
            "type": "string",
            "description": "QGIS expression choosing which features to change: \"name = 'Lenina'\"",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_editable(params.get("layer_name") or "")
        values = _checked_values(layer, params.get("values"))
        matched = _matched_count(layer, (params.get("filter") or "").strip())
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["values"] = values
        prepared["matched_estimate"] = matched
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        values = params.get("values") or {}
        fields = ", ".join(sorted(values)) if isinstance(values, dict) else ""
        matched = params.get("matched_estimate")
        if isinstance(matched, int):
            return tr("Updating {0} feature(s) of '{1}': {2}.").format(matched, layer_name, fields)
        return tr("Updating features of '{0}': {1}.").format(layer_name, fields)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_editable(params.get("layer_name") or "")
        values = _checked_values(layer, params.get("values"))
        indexes = {name: layer.fields().indexFromName(name) for name in values}
        request = build_request((params.get("filter") or "").strip(), layer)
        build_context(layer)
        if not layer.startEditing():
            raise ValueError(
                f"Layer '{layer.name()}' cannot be switched into editing mode — "
                "its data source is read-only. Extract what you need into a new editable "
                "layer instead: native:extractbyexpression with the features to KEEP, "
                "then remove the old layer."
            )
        updated = 0
        for feature in layer.getFeatures(request):
            for name, value in values.items():
                layer.changeAttributeValue(feature.id(), indexes[name], value)
            updated += 1
        if not layer.commitChanges():
            reason = "; ".join(layer.commitErrors() or []) or "provider refused"
            layer.rollBack()
            raise ValueError(COMMIT_FAILED.format(reason=reason))
        return {"layer": layer.name(), "updated": updated, "fields": sorted(values)}


def _require_editable(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no attributes to edit.")
    return layer


def _checked_values(layer: QgsVectorLayer, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("values must be a non-empty object of field-to-value pairs.")
    names = layer.fields().names()
    unknown = sorted(name for name in raw if name not in names)
    if unknown:
        raise ValueError(
            f"Layer '{layer.name()}' has no field(s) {', '.join(unknown)}. {suggest_fields(unknown, names)}"
        )
    return dict(raw)


def _matched_count(layer: QgsVectorLayer, filter_text: str) -> int:
    request = build_request(filter_text, layer)
    matched = 0
    for _ in layer.getFeatures(request):
        matched += 1
        if matched > MAX_SCAN:
            raise ValueError(
                f"More than {MAX_SCAN} features match — narrow the filter before editing that much at once."
            )
    if matched == 0:
        raise ValueError(
            "No features match this filter, so there is nothing to update. "
            "Check the values with get_field_values or query_layer first."
        )
    return matched
