from contextlib import suppress
from typing import Any

from qgis.core import QgsFeatureRequest, QgsProject

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layer_meta import selected_count
from ai_agent.qgis_tools.common.layers import layer_reference
from ai_agent.qgis_tools.common.values import plain_value

SAMPLE_LIMIT = 10
MAX_VALUE_CHARS = 120
NOTHING_SELECTED = "Nothing is selected on the map right now."
HOW_TO_USE = "To compute over just these features, call query_layer with selected_only=true."


class GetSelectionTool(BaseTool):
    name = "get_selection"
    description = (
        "Show what the user has selected on the map: which layers hold selected "
        "features, how many, and a sample of their attributes. Call it whenever "
        "the request says 'selected', 'these', 'highlighted' or points at "
        "something on screen."
    )
    skill = "inspect"
    safety = SAFETY_READ
    external_effect = False
    network_access = False
    egress = EGRESS_FEATURE_VALUES
    examples = ["What did I select?", "Compute the area of the selected polygons"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the current selection.")

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        return tr_n("%n feature(s) selected", int(payload.get("selected_total") or 0))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selections = []
        total = 0
        for layer in QgsProject.instance().mapLayers().values():
            count = selected_count(layer)
            if not count:
                continue
            total += count
            selections.append(
                {
                    **layer_reference(layer),
                    "count": count,
                    "features": _sample(layer),
                }
            )
        if not selections:
            return {"selected_total": 0, "note": NOTHING_SELECTED}
        return {"selected_total": total, "selections": selections, "note": HOW_TO_USE}


def _sample(layer: Any) -> list[dict[str, Any]]:
    try:
        names = layer.fields().names()
        # Only the sample is read: selectedFeatures() would load every selected
        # feature, with geometry, just to show ten of them.
        features = layer.getSelectedFeatures(QgsFeatureRequest().setLimit(SAMPLE_LIMIT).setNoGeometry())
    except Exception:
        return []
    sampled = []
    for feature in features:
        if len(sampled) >= SAMPLE_LIMIT:
            break
        attributes = {}
        for name in names:
            with suppress(Exception):
                attributes[name] = _short(plain_value(feature[name]))
        sampled.append(attributes)
    return sampled


def _short(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + "…"
    return value
