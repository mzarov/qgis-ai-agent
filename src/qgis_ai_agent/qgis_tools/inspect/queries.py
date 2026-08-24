from typing import Any

from qgis_ai_agent.qgis_tools.inspect.aggregates import compute
from qgis_ai_agent.qgis_tools.inspect.expressions import (
    evaluate,
    parse_order_by,
    plain_value,
    prepared,
    sort_key,
)

MAX_SCAN = 50000
DEFAULT_ROW_LIMIT = 20
MAX_ROW_LIMIT = 200
MAX_GROUPS = 50
SCAN_LIMIT_MESSAGE = (
    "Под условие подпадает больше {limit} объектов, и точный ответ по ним не посчитать. "
    "Сузьте выборку параметром filter."
)


def run_aggregate(layer, request, context, params, aggregate: str) -> dict[str, Any]:
    expression_text = (params.get("expression") or "").strip()
    group_text = (params.get("group_by") or "").strip()
    value_expression = prepared(expression_text, "expression", context) if expression_text else None
    group_expression = prepared(group_text, "group_by", context) if group_text else None

    matched = 0
    values: list[Any] = []
    groups: dict[Any, list[Any]] = {}
    for feature in layer.getFeatures(request):
        matched += 1
        if matched > MAX_SCAN:
            raise ValueError(SCAN_LIMIT_MESSAGE.format(limit=MAX_SCAN))
        value = evaluate(value_expression, context, feature) if value_expression else None
        if group_expression is None:
            values.append(value)
        else:
            groups.setdefault(evaluate(group_expression, context, feature), []).append(value)

    info: dict[str, Any] = {"aggregate": aggregate, "matched": matched}
    if expression_text:
        info["expression"] = expression_text
    if group_expression is None:
        info["value"] = compute(aggregate, values, matched)
        return info
    info["group_by"] = group_text
    info["groups"] = _build_groups(aggregate, groups)
    if len(groups) > MAX_GROUPS:
        info["groups_note"] = f"показаны первые {MAX_GROUPS} групп из {len(groups)}"
    return info


def run_rows(layer, request, context, params) -> dict[str, Any]:
    order_text, ascending = parse_order_by(params.get("order_by") or "")
    order_expression = prepared(order_text, "order_by", context) if order_text else None
    limit = resolve_limit(params.get("limit"))
    wanted = _wanted_fields(layer, params.get("fields"))

    collected = []
    for feature in layer.getFeatures(request):
        if len(collected) >= MAX_SCAN:
            raise ValueError(SCAN_LIMIT_MESSAGE.format(limit=MAX_SCAN))
        key = evaluate(order_expression, context, feature) if order_expression else None
        collected.append((key, _attributes(feature, wanted)))

    if order_expression is not None:
        collected.sort(key=lambda item: sort_key(item[0]), reverse=not ascending)
    info: dict[str, Any] = {
        "matched": len(collected),
        "shown": min(limit, len(collected)),
        "features": [attributes for _, attributes in collected[:limit]],
    }
    if order_text:
        info["order_by"] = f"{order_text} {'ASC' if ascending else 'DESC'}"
    return info


def resolve_limit(raw: Any) -> int:
    try:
        value = int(raw) if raw is not None else DEFAULT_ROW_LIMIT
    except (TypeError, ValueError):
        value = DEFAULT_ROW_LIMIT
    return max(1, min(value, MAX_ROW_LIMIT))


def _build_groups(aggregate: str, groups: dict[Any, list[Any]]) -> list[dict[str, Any]]:
    ordered = sorted(groups.items(), key=lambda item: sort_key(item[0]))
    return [
        {"group": group, "count": len(items), "value": compute(aggregate, items, len(items))}
        for group, items in ordered[:MAX_GROUPS]
    ]


def _attributes(feature, wanted: list[str] | None) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    try:
        names = feature.fields().names()
    except Exception:
        return attributes
    for name in names:
        if wanted is None or name in wanted:
            attributes[name] = plain_value(feature[name])
    return attributes


def _wanted_fields(layer, raw: Any) -> list[str] | None:
    if not isinstance(raw, list) or not raw:
        return None
    available = set(layer.fields().names())
    wanted = [str(name) for name in raw if str(name) in available]
    return wanted or None
