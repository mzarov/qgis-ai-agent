from typing import Any

from qgis.core import QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.expressions import build_context, build_request
from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.inspect.aggregates import AGGREGATE_FUNCTIONS
from ai_agent.qgis_tools.inspect.queries import DEFAULT_ROW_LIMIT, run_aggregate, run_rows


class QueryLayerTool(BaseTool):
    name = "query_layer"
    description = (
        "Query layer data with the QGIS expression language: count features matching a "
        "condition, aggregate, group, sort, take the first N. "
        "ANY question about how many, largest, average, total or top is answered by this tool. "
        "Length and area come straight from the geometry through the $length and $area "
        "expressions: a separate length field usually does NOT exist, so do not look for one."
    )
    skill = "inspect"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    constraints = [
        "The layer must exist and be a vector layer",
        "Field names in expressions are case sensitive",
    ]
    examples = [
        "How many roads of type motorway are there?",
        "Top 5 cities by population",
        "Which river is the longest?",
        "Total area of the lakes",
    ]
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
            "description": "Selection condition as a QGIS expression: \"highway = 'motorway'\"",
            "required": False,
        },
        {
            "name": "aggregate",
            "type": "string",
            "description": "Aggregate function. Without it the features themselves are returned.",
            "required": False,
            "enum": list(AGGREGATE_FUNCTIONS),
        },
        {
            "name": "expression",
            "type": "string",
            "description": 'Field or expression to aggregate: "population", "$length", "$area"',
            "required": False,
        },
        {
            "name": "group_by",
            "type": "string",
            "description": "Field or expression to group the result by",
            "required": False,
        },
        {
            "name": "order_by",
            "type": "string",
            "description": 'Feature ordering: "population DESC". Only without aggregate.',
            "required": False,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"How many features to return (default {DEFAULT_ROW_LIMIT})",
            "required": False,
        },
        {
            "name": "fields",
            "type": "array",
            "items": {"type": "string"},
            "description": "Which fields to show for the features. All of them by default.",
            "required": False,
        },
        {
            "name": "selected_only",
            "type": "boolean",
            "description": "Work only with the features the user selected on the map",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        aggregate = (params.get("aggregate") or "").strip()
        condition = (params.get("filter") or "").strip()
        action = tr("computing {0}").format(aggregate) if aggregate else tr("selecting features")
        where = tr(" where {0}").format(condition) if condition else ""
        return tr("Layer '{0}': {1}{2}.").format(layer_name, action, where)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        if not isinstance(layer, QgsVectorLayer):
            raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it cannot be queried.")

        context = build_context(layer)
        request = build_request(params.get("filter") or "", layer)
        if params.get("selected_only"):
            _restrict_to_selection(layer, request)
        aggregate = (params.get("aggregate") or "").strip().lower()

        result: dict[str, Any] = {"layer_name": layer.name()}
        condition = (params.get("filter") or "").strip()
        if condition:
            result["filter"] = condition
        if params.get("selected_only"):
            result["selected_only"] = True
        if aggregate:
            result.update(run_aggregate(layer, request, context, params, aggregate))
        else:
            result.update(run_rows(layer, request, context, params))
        return result


def _restrict_to_selection(layer: QgsVectorLayer, request: Any) -> None:
    try:
        ids = list(layer.selectedFeatureIds())
    except Exception:
        ids = []
    if not ids:
        raise ValueError(
            f"Nothing is selected on layer '{layer.name()}'. Ask the user to select "
            "features first, or drop selected_only."
        )
    request.setFilterFids(ids)
