from typing import Any

from qgis.core import QgsVectorLayer

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.expressions import compile_expression
from ai_agent.qgis_tools.common.layers import find_layer_by_name, layer_reference

MAX_FLASH = 200
NOTHING_MATCHED = (
    "Nothing matches that condition, so the selection was left alone. Check the "
    "values with get_field_values before selecting."
)
SHOWN_NOTE = "The matching features are now selected and highlighted on the map."
REPLACED_NOTE = (
    "The user's previous selection of {count} features on this layer was replaced. "
    "Say so in the answer; it cannot be restored automatically."
)


class SelectFeaturesTool(BaseTool):
    name = "select_features"
    description = (
        "Select features on the map by a condition and zoom to them, so the user "
        "can see the answer instead of only reading it. Selection is a view "
        "state — it changes nothing in the data."
    )
    skill = "inspect"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["The layer must exist and be a vector layer"]
    examples = ["Show me the motorways", "Highlight the districts with no population data"]
    params_schema = [
        params.layer_name(),
        {
            "name": "filter",
            "type": "string",
            "description": "QGIS expression choosing what to select: \"highway = 'motorway'\"",
            "required": True,
        },
        {
            "name": "zoom",
            "type": "boolean",
            "description": "Zoom the map to the selection (true by default)",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return tr("Selecting features in '{0}'.").format(layer_name)

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        return tr_n("%n feature(s) selected", int(payload.get("selected") or 0))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "")
        expression = str(params.get("filter") or "").strip()
        if not expression:
            raise ValueError("filter is required — an expression saying what to select.")
        compile_expression(expression, "filter", layer)
        previous_ids = _selected_ids(layer)
        previous = len(previous_ids)
        layer.selectByExpression(expression)
        selected = _selected_count(layer)
        result: dict[str, Any] = {**layer_reference(layer), "selected": selected, "previous_selection_count": previous}
        if not selected:
            # selectByExpression clears the selection when nothing matches;
            # an empty answer must not cost the user what they had selected.
            if previous_ids:
                layer.selectByIds(previous_ids)
            return {**result, "note": NOTHING_MATCHED}
        if params.get("zoom") is not False:
            _zoom_to_selection(layer)
        _flash(layer)
        note = SHOWN_NOTE
        if previous:
            note += " " + REPLACED_NOTE.format(count=previous)
        return {**result, "note": note}


def _require_vector(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, there is nothing to select.")
    return layer


def _selected_ids(layer: Any) -> list[int]:
    try:
        return [int(identifier) for identifier in layer.selectedFeatureIds()]
    except Exception:
        return []


def _selected_count(layer: Any) -> int:
    try:
        return int(layer.selectedFeatureCount())
    except Exception:
        return 0


def _zoom_to_selection(layer: Any) -> None:
    try:
        from qgis.utils import iface

        iface.mapCanvas().zoomToSelected(layer)
    except Exception:
        return


def _flash(layer: Any) -> None:
    try:
        from qgis.utils import iface

        ids = list(layer.selectedFeatureIds())[:MAX_FLASH]
        iface.mapCanvas().flashFeatureIds(layer, ids)
    except Exception:
        return
