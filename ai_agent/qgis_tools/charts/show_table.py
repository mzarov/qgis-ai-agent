from typing import Any

from qgis.core import QgsFeatureRequest, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.charts.spec import MAX_TABLE_COLUMNS, MAX_TABLE_ROWS, attach, table
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.expressions import build_request, parse_order_by
from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.common.values import clamp_limit, plain_value, suggest_fields

DEFAULT_ROWS = 20
PREVIEW_ROWS = 3


class ShowTableTool(BaseTool):
    name = "show_table"
    description = (
        "Show features of a vector layer as a table in the chat: chosen fields, a filter, sorted, "
        "the first N rows. The person sees every row; you get the column names and the first rows."
    )
    skill = "charts"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = [f"At most {MAX_TABLE_ROWS} rows and {MAX_TABLE_COLUMNS} columns"]
    examples = ["Show the ten largest districts with name and population", "Table of the cafes without a name"]
    params_schema = [
        params.layer_name(),
        {
            "name": "fields",
            "type": "array",
            "items": {"type": "string"},
            "description": "Columns to show, in order; default the first fields",
            "required": False,
        },
        {"name": "filter", "type": "string", "description": "QGIS expression selecting rows", "required": False},
        {
            "name": "order_by",
            "type": "string",
            "description": 'Field to sort by, with "desc" for largest first: "pop2020 desc"',
            "required": False,
        },
        {"name": "limit", "type": "integer", "description": f"Rows, default {DEFAULT_ROWS}", "required": False},
        {"name": "title", "type": "string", "description": "Table title", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _layer(params)
        _columns(layer, params)
        build_request(str(params.get("filter") or ""), layer)
        _order(layer, params)
        return params

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Showing a table of '{0}'.").format(str(params.get("layer_name") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _layer(params)
        columns = _columns(layer, params)
        request = build_request(str(params.get("filter") or ""), layer)
        request.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        request.setSubsetOfAttributes(columns, layer.fields())
        field, ascending = _order(layer, params)
        if field:
            request.addOrderBy(f'"{field}"', ascending)
        limit = clamp_limit(params.get("limit"), DEFAULT_ROWS, MAX_TABLE_ROWS)
        request.setLimit(limit)
        rows = [[plain_value(feature[name]) for name in columns] for feature in layer.getFeatures(request)]
        total = layer.featureCount() if not str(params.get("filter") or "").strip() else len(rows)
        title = str(params.get("title") or "").strip() or layer.name()
        spec = table(title, columns, rows, total)
        result = {"shown": "table", "columns": columns, "rows_shown": len(rows), "first_rows": rows[:PREVIEW_ROWS]}
        return attach(result, spec)


def _layer(params: dict[str, Any]) -> QgsVectorLayer:
    layer = find_layer_by_name(params.get("layer_name") or "")
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer.name()}' is not a vector layer; it has no attribute table.")
    return layer


def _columns(layer: QgsVectorLayer, params: dict[str, Any]) -> list[str]:
    available = list(layer.fields().names())
    raw = params.get("fields") or []
    if not isinstance(raw, list) or not raw:
        return available[:MAX_TABLE_COLUMNS]
    wanted = [str(name) for name in raw]
    unknown = [name for name in wanted if name not in available]
    if unknown:
        raise ValueError(f"No field {', '.join(unknown)} in '{layer.name()}'. {suggest_fields(unknown, available)}")
    return wanted[:MAX_TABLE_COLUMNS]


def _order(layer: QgsVectorLayer, params: dict[str, Any]) -> tuple[str, bool]:
    field, ascending = parse_order_by(str(params.get("order_by") or ""))
    if field and field not in layer.fields().names():
        raise ValueError(
            f"order_by names '{field}', which is not a field. {suggest_fields([field], layer.fields().names())}"
        )
    return field, ascending
