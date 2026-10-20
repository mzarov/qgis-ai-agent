from contextlib import suppress
from typing import Any

from qgis.core import QgsDistanceArea, QgsProject, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.common.expressions import build_context, build_request, evaluate_raw, prepared
from ai_agent.qgis_tools.common.layers import bind_layer_reference, find_layer_by_id, find_layer_by_name
from ai_agent.qgis_tools.common.values import plain_value, suggest_fields
from ai_agent.qgis_tools.edit.pinned import pinned_features

MAX_SCAN = 50000


class UpdateAttributesTool(BaseTool):
    name = "update_attributes"
    description = (
        "Change attribute values of existing features in place, on every feature matching "
        "the filter: set fields to constants (values) or to a QGIS expression computed per "
        "feature (expressions, e.g. $area / 10000; $area and $length measure on the project "
        "ellipsoid). This edits the underlying data. "
        "The matches are counted when the step is queued and the user sees the count before "
        "confirming, so there is no need to count them first."
    )
    skill = "edit"
    safety = SAFETY_DESTRUCTIVE
    egress = EGRESS_METADATA
    network_access = False
    external_effect = True
    constraints = [
        "The layer must be an editable vector layer",
        "The fields must exist when the step is queued: a field added in this run needs apply_now first",
        "values holds constants; a computed value goes in expressions",
        "Without a filter every feature is touched — pass one whenever possible",
    ]
    examples = ["Set type to 'park' for the selected polygons", "Fix the misspelled city name"]
    params_schema = [
        params.layer_name(),
        params.layer_id(),
        {
            "name": "values",
            "type": "object",
            "description": 'Constant new values per field, e.g. {"type": "park", "verified": 1}',
            "required": False,
        },
        {
            "name": "expressions",
            "type": "object",
            "description": 'A QGIS expression per field, evaluated for each feature, e.g. {"area_ha": "$area / 10000"}',
            "required": False,
        },
        {
            "name": "filter",
            "type": "string",
            "description": "QGIS expression choosing which features to change: \"name = 'Lenina'\"",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_editable(params.get("layer_name") or "", params.get("layer_id") or "")
        values, expressions = _checked_changes(layer, params)
        feature_ids = _matched_ids(layer, (params.get("filter") or "").strip())
        prepared = bind_layer_reference(params, layer)
        prepared["values"] = values
        prepared["expressions"] = expressions
        prepared["matched_estimate"] = len(feature_ids)
        prepared["_feature_ids"] = feature_ids
        return prepared

    def detail_call(self, params: dict[str, Any]) -> str:
        values = params.get("values")
        lines = [
            tr("Layer: {0}").format(str(params.get("layer_name") or "").strip()),
            _filter_line(params.get("filter")),
        ]
        matched = params.get("matched_estimate")
        if isinstance(matched, int):
            lines.append(tr("Features to change: {0}").format(matched))
        lines.append(tr("New values:"))
        if isinstance(values, dict):
            lines.extend(f"  {name} = {value!r}" for name, value in values.items())
        expressions = params.get("expressions")
        if isinstance(expressions, dict):
            lines.extend(f"  {name} = {text}" for name, text in expressions.items())
        return "\n".join(lines)

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        changed = [*_names(params.get("values")), *_names(params.get("expressions"))]
        fields = ", ".join(sorted(changed))
        matched = params.get("matched_estimate")
        if isinstance(matched, int):
            return tr("Updating {0} feature(s) of '{1}': {2}.").format(matched, layer_name, fields)
        return tr("Updating features of '{0}': {1}.").format(layer_name, fields)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_editable(params.get("layer_name") or "", params.get("layer_id") or "")
        values, expressions = _checked_changes(layer, params)
        indexes = {name: layer.fields().indexFromName(name) for name in [*values, *expressions]}
        features = _prepared_features(layer, params)
        context = build_context(layer)
        compiled = {name: _measuring(prepared(text, name, context, layer), layer) for name, text in expressions.items()}
        # Every value is computed before the first write: a failing expression leaves nothing changed.
        rows = []
        for feature in features:
            computed = {name: evaluate_raw(expr, context, feature) for name, expr in compiled.items()}
            row = {name: _stored(layer, name, value) for name, value in {**values, **computed}.items()}
            rows.append((feature.id(), row))
        with edit_session(layer, "the attribute edits"):
            for feature_id, row in rows:
                for name, value in row.items():
                    if not layer.changeAttributeValue(feature_id, indexes[name], value):
                        raise ValueError(f"QGIS refused to update field '{name}' on feature {feature_id}.")
        return {"layer": layer.name(), "updated": len(features), "fields": sorted([*values, *expressions])}


def _require_editable(layer_name: str, layer_id: str = "") -> QgsVectorLayer:
    layer = find_layer_by_id(layer_id) if layer_id else find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no attributes to edit.")
    return layer


def _checked_changes(layer: QgsVectorLayer, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    values, expressions = params.get("values") or {}, params.get("expressions") or {}
    if not isinstance(values, dict) or not isinstance(expressions, dict) or not (values or expressions):
        raise ValueError(
            'Give values (constants, {"type": "park"}) or expressions (computed, {"area_ha": "$area / 10000"}).'
        )
    both = sorted(set(values) & set(expressions))
    if both:
        raise ValueError(f"Field(s) {', '.join(both)} are in both values and expressions; keep each in one.")
    names = layer.fields().names()
    unknown = sorted(name for name in [*values, *expressions] if name not in names)
    if unknown:
        raise ValueError(
            f"Layer '{layer.name()}' has no field(s) {', '.join(unknown)}. {suggest_fields(unknown, names)} "
            "A field added in this run exists only once applied: call apply_now first."
        )
    for name, value in values.items():
        _check_convertible(layer, name, value)
    context = build_context(layer)
    for name, text in expressions.items():
        prepared(str(text), name, context, layer)
    return dict(values), {name: str(text) for name, text in expressions.items()}


def _measuring(expression: Any, layer: QgsVectorLayer) -> Any:
    # $area and $length need the project's ellipsoid and units, as the field calculator sets them.
    project = QgsProject.instance()
    with suppress(Exception):
        calculator = QgsDistanceArea()
        calculator.setSourceCrs(layer.crs(), project.transformContext())
        calculator.setEllipsoid(project.ellipsoid())
        expression.setGeomCalculator(calculator)
        expression.setDistanceUnits(project.distanceUnits())
        expression.setAreaUnits(project.areaUnits())
    return expression


def _stored(layer: QgsVectorLayer, name: str, value: Any) -> Any:
    # As the field calculator does: a date reaches a date field as a date, and text as the field's type.
    try:
        return layer.fields().field(name).convertCompatible(value)
    except Exception:
        return value if value is None or isinstance(value, (str, int, float, bool)) else plain_value(value)


def _names(raw: Any) -> list[str]:
    return [str(name) for name in raw] if isinstance(raw, dict) else []


def _check_convertible(layer: QgsVectorLayer, name: str, value: Any) -> None:
    try:
        field = layer.fields().field(name)
        convert = field.convertCompatible
    except Exception:
        return
    try:
        convert(value)
    except ValueError as err:
        kind = ""
        with suppress(Exception):
            kind = f" ({field.typeName()})" if field.typeName() else ""
        raise ValueError(
            f"Value {value!r} does not fit field '{name}'{kind}: {err}. "
            "Give a value of the field's type, or null to clear it."
        ) from None


def _filter_line(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return tr("Filter: none, every feature is changed")
    return tr("Filter: {0}").format(text)


def _matched_ids(layer: QgsVectorLayer, filter_text: str) -> list[int]:
    request = build_request(filter_text, layer)
    matched = []
    for feature in layer.getFeatures(request):
        matched.append(feature.id())
        if len(matched) > MAX_SCAN:
            raise ValueError(
                f"More than {MAX_SCAN} features match — narrow the filter before editing that much at once."
            )
    if not matched:
        raise ValueError(
            "No features match this filter, so there is nothing to update. "
            "Check the values with get_field_values or query_layer first."
        )
    return matched


def _prepared_features(layer: QgsVectorLayer, params: dict[str, Any]) -> list[Any]:
    pinned = params.get("_feature_ids")
    text = (params.get("filter") or "").strip()
    if not isinstance(pinned, list):
        return list(layer.getFeatures(build_request(text, layer)))
    return pinned_features(layer, pinned, build_request(text, layer) if text else None, "updated")
