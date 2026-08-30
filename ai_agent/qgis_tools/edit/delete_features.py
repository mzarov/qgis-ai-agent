from typing import Any

from qgis.core import QgsFeatureRequest, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.common.expressions import build_request
from ai_agent.qgis_tools.common.layers import bind_layer_reference, find_layer_by_id, find_layer_by_name

MAX_DELETE = 10000
ALL_MARKER = "all"
COMMIT_FAILED = "QGIS could not commit the deletion: {reason}. The layer was rolled back and nothing was deleted."


class DeleteFeaturesTool(BaseTool):
    name = "delete_features"
    description = (
        "Delete features from a vector layer permanently. Requires a filter "
        "expression choosing what to delete; deleting everything needs the "
        "literal filter 'all'. This removes data from the underlying source."
    )
    skill = "edit"
    safety = SAFETY_DESTRUCTIVE
    external_effect = True
    constraints = [
        "The layer must be an editable vector layer",
        "The filter is mandatory — 'all' is the explicit way to delete everything",
        f"At most {MAX_DELETE} features per call",
    ]
    examples = ["Delete the features with an empty name", "Remove the duplicates I selected"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "layer_id",
            "type": "string",
            "description": "Stable layer id from list_layers; required when names are duplicated",
            "required": False,
        },
        {
            "name": "filter",
            "type": "string",
            "description": "QGIS expression choosing what to delete, or the literal 'all'",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "", params.get("layer_id") or "")
        ids = _matched_ids(layer, params.get("filter") or "")
        prepared = bind_layer_reference(params, layer)
        prepared["matched_estimate"] = len(ids)
        prepared["_feature_ids"] = ids
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        matched = params.get("matched_estimate")
        if isinstance(matched, int):
            return tr("Deleting {0} feature(s) from '{1}'.").format(matched, layer_name)
        return tr("Deleting features from '{0}'.").format(layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "", params.get("layer_id") or "")
        ids = _prepared_ids(layer, params)
        if not layer.startEditing():
            raise ValueError(
                f"Layer '{layer.name()}' cannot be switched into editing mode — "
                "its data source is read-only. Extract what you need into a new editable "
                "layer instead: native:extractbyexpression with the features to KEEP, "
                "then remove the old layer."
            )
        layer.deleteFeatures(ids)
        if not layer.commitChanges():
            reason = "; ".join(layer.commitErrors() or []) or "provider refused"
            layer.rollBack()
            raise ValueError(COMMIT_FAILED.format(reason=reason))
        return {"layer": layer.name(), "deleted": len(ids)}


def _require_vector(layer_name: str, layer_id: str = "") -> QgsVectorLayer:
    layer = find_layer_by_id(layer_id) if layer_id else find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, there is nothing to delete.")
    return layer


def _matched_ids(layer: QgsVectorLayer, raw_filter: str) -> list[int]:
    text = (raw_filter or "").strip()
    if not text:
        raise ValueError(
            "A filter is required: deleting needs an explicit choice of features. "
            "To delete every feature, pass the literal filter 'all'."
        )
    request = build_request("" if text.lower() == ALL_MARKER else text, layer)
    ids = []
    for feature in layer.getFeatures(request):
        ids.append(feature.id())
        if len(ids) > MAX_DELETE:
            raise ValueError(
                f"More than {MAX_DELETE} features match — narrow the filter; bulk wipes need a manual step."
            )
    if not ids:
        raise ValueError("No features match this filter, so there is nothing to delete.")
    return ids


def _prepared_ids(layer: QgsVectorLayer, params: dict[str, Any]) -> list[int]:
    pinned = params.get("_feature_ids")
    if not isinstance(pinned, list):
        return _matched_ids(layer, params.get("filter") or "")
    wanted = {int(identifier) for identifier in pinned}
    request = QgsFeatureRequest()
    request.setFilterFids(list(wanted))
    found = {feature.id() for feature in layer.getFeatures(request) if feature.id() in wanted}
    missing = wanted - found
    if missing:
        raise ValueError(
            f"{len(missing)} feature(s) selected during planning no longer exist. "
            "Nothing was deleted; review the layer and plan again."
        )
    return [int(identifier) for identifier in pinned]
