from typing import Any

from qgis.core import QgsFeatureRequest, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.charts.spec import MAX_CATEGORIES, attach, chart, fold_other
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.expressions import build_context, build_request, compile_expression, evaluate
from ai_agent.qgis_tools.common.layers import find_layer_by_name

AGGREGATES = ("count", "sum", "mean", "min", "max")
CHART_KINDS = ("auto", "bar", "pie", "histogram")
DEFAULT_BINS = 10
MAX_BINS = 30
DEFAULT_TOP = 12
MAX_FEATURES = 200_000
EMPTY = "(empty)"


class ChartLayerTool(BaseTool):
    name = "chart_layer"
    description = (
        "Compute a chart from a vector layer and draw it in the chat: a histogram of a numeric "
        "field or expression, or a value per category (count, sum, mean, min, max), as bars or a pie."
    )
    skill = "charts"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = [
        "value is a field or expression such as pop2020 or $area / 1e6",
        "Without group_by the chart is a histogram of value",
    ]
    examples = [
        "Show the distribution of district population",
        "Chart the total road length by type",
        "Pie of land use classes by area",
    ]
    params_schema = [
        params.layer_name(),
        {
            "name": "value",
            "type": "string",
            "description": "Field or expression to measure; leave out to count features per group",
            "required": False,
        },
        {
            "name": "group_by",
            "type": "string",
            "description": "Field or expression for the categories",
            "required": False,
        },
        {
            "name": "aggregate",
            "type": "string",
            "description": "How a group's values combine; default sum with value, count without",
            "enum": list(AGGREGATES),
            "required": False,
        },
        {"name": "kind", "type": "string", "description": "Chart type", "enum": list(CHART_KINDS), "required": False},
        {"name": "filter", "type": "string", "description": "QGIS expression selecting features", "required": False},
        {
            "name": "bins",
            "type": "integer",
            "description": f"Histogram bins, default {DEFAULT_BINS}",
            "required": False,
        },
        {
            "name": "top",
            "type": "integer",
            "description": f"Largest groups shown, default {DEFAULT_TOP}",
            "required": False,
        },
        {"name": "title", "type": "string", "description": "Chart title", "required": False},
        {"name": "unit", "type": "string", "description": "Unit of the values", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _layer(params)
        _setup(layer, params)
        return params

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Charting '{0}'.").format(str(params.get("layer_name") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _layer(params)
        value, group, aggregate, kind = _setup(layer, params)
        rows = _rows(layer, params, value, group)
        if group is None:
            spec = _histogram(rows, params, layer)
        else:
            spec = _grouped(rows, params, aggregate, kind, layer)
        series = spec["series"][0]["values"]
        result = {
            "shown": "chart",
            "features": len(rows),
            "labels": spec["labels"],
            "values": [round(value, 6) if value is not None else None for value in series],
        }
        return attach(result, spec)


def _layer(params: dict[str, Any]) -> QgsVectorLayer:
    layer = find_layer_by_name(params.get("layer_name") or "")
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer.name()}' is not a vector layer; charts read attribute values.")
    return layer


def _setup(layer: QgsVectorLayer, params: dict[str, Any]) -> tuple[Any, Any, str, str]:
    value_text = str(params.get("value") or "").strip()
    group_text = str(params.get("group_by") or "").strip()
    kind = str(params.get("kind") or "auto").strip().lower()
    if kind not in CHART_KINDS:
        raise ValueError(f"kind is one of {', '.join(CHART_KINDS)}.")
    if not group_text and not value_text:
        raise ValueError("Give value for a histogram, or group_by (and optionally value) for categories.")
    if not group_text and kind == "pie":
        raise ValueError("A pie needs group_by: it shows shares of categories.")
    aggregate = str(params.get("aggregate") or ("sum" if value_text else "count")).strip().lower()
    if aggregate not in AGGREGATES:
        raise ValueError(f"aggregate is one of {', '.join(AGGREGATES)}.")
    if aggregate != "count" and not value_text:
        raise ValueError(f"aggregate {aggregate} needs value: the field or expression to {aggregate}.")
    build_request(str(params.get("filter") or ""), layer)
    value = compile_expression(value_text, "value", layer) if value_text else None
    group = compile_expression(group_text, "group_by", layer) if group_text else None
    return value, group, aggregate, kind


def _rows(layer: QgsVectorLayer, params: dict[str, Any], value: Any, group: Any) -> list[tuple[Any, Any]]:
    request = build_request(str(params.get("filter") or ""), layer)
    request.setLimit(MAX_FEATURES)
    needs_geometry = any(expression is not None and expression.needsGeometry() for expression in (value, group))
    if not needs_geometry:
        request.setFlags(QgsFeatureRequest.Flag.NoGeometry)
    context = build_context(layer)
    for expression in (value, group):
        if expression is not None:
            expression.prepare(context)
    rows = []
    for feature in layer.getFeatures(request):
        rows.append(
            (
                evaluate(value, context, feature) if value is not None else None,
                evaluate(group, context, feature) if group is not None else None,
            )
        )
    if not rows:
        raise ValueError("No feature matches; nothing to chart. Check the filter.")
    return rows


def _histogram(rows: list[tuple[Any, Any]], params: dict[str, Any], layer: QgsVectorLayer) -> dict[str, Any]:
    numbers = [
        float(value) for value, _group in rows if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if not numbers:
        raise ValueError("value gave no numbers; a histogram needs a numeric field or expression.")
    bins = max(1, min(int(params.get("bins") or DEFAULT_BINS), MAX_BINS))
    low, high = min(numbers), max(numbers)
    width = (high - low) / bins or 1.0
    counts = [0.0] * bins
    for number in numbers:
        counts[min(int((number - low) / width), bins - 1)] += 1
    labels = [f"{_short(low + index * width)}–{_short(low + (index + 1) * width)}" for index in range(bins)]
    value_text = str(params.get("value") or "")
    title = str(params.get("title") or "").strip() or f"{layer.name()}: {value_text}"
    return chart("histogram", title, labels, [{"name": value_text, "values": counts}], value_text, "features")


def _grouped(
    rows: list[tuple[Any, Any]], params: dict[str, Any], aggregate: str, kind: str, layer: QgsVectorLayer
) -> dict[str, Any]:
    groups: dict[str, list[float]] = {}
    for value, group in rows:
        key = EMPTY if group is None or str(group).strip() == "" else str(group)
        bucket = groups.setdefault(key, [])
        if aggregate == "count":
            bucket.append(1.0)
        elif _is_number(value):
            bucket.append(float(value))
    totals = {key: _combine(values, aggregate) for key, values in groups.items()}
    ordered = sorted(totals, key=lambda key: -(totals[key] or 0))
    top = max(1, min(int(params.get("top") or DEFAULT_TOP), MAX_CATEGORIES))
    labels, values = (
        fold_other(ordered, [totals[key] for key in ordered], top)
        if aggregate in ("count", "sum")
        else (
            ordered[:top],
            [totals[key] for key in ordered[:top]],
        )
    )
    chosen = "pie" if kind == "pie" else "bar"
    value_text = str(params.get("value") or "features")
    title = str(params.get("title") or "").strip() or f"{layer.name()}: {aggregate} of {value_text}"
    unit = str(params.get("unit") or "")
    return chart(chosen, title, labels, [{"name": f"{aggregate} {value_text}", "values": values}], "", "", unit)


def _combine(values: list[float], aggregate: str) -> float | None:
    if not values:
        return None
    if aggregate in ("count", "sum"):
        return sum(values)
    if aggregate == "mean":
        return sum(values) / len(values)
    return min(values) if aggregate == "min" else max(values)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _short(number: float) -> str:
    return f"{number:,.3g}"
