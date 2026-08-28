from typing import Any

from qgis.core import QgsVectorLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.expressions import compile_expression
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name

MAX_FLASH = 200
NOTHING_MATCHED = (
    "Nothing matches that condition, so the selection was left alone. Check the "
    "values with get_field_values before selecting."
)
SHOWN_NOTE = "The matching features are now selected and highlighted on the map."


class SelectFeaturesTool(BaseTool):
    name = "select_features"
    description = (
        "Select features on the map by a condition and zoom to them, so the user "
        "can see the answer instead of only reading it. Selection is a view "
        "state — it changes nothing in the data."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["The layer must exist and be a vector layer"]
    examples = ["Show me the motorways", "Highlight the districts with no population data"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
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

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "")
        expression = str(params.get("filter") or "").strip()
        if not expression:
            raise ValueError("filter is required — an expression saying what to select.")
        compile_expression(expression, "filter", layer)
        layer.selectByExpression(expression)
        selected = int(layer.selectedFeatureCount())
        if not selected:
            return {"layer": layer.name(), "selected": 0, "note": NOTHING_MATCHED}
        if params.get("zoom") is not False:
            _zoom_to_selection(layer)
        _flash(layer)
        return {"layer": layer.name(), "selected": selected, "note": SHOWN_NOTE}


def _require_vector(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, there is nothing to select.")
    return layer


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
