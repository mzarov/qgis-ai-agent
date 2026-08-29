from typing import Any

from qgis.core import QgsFeatureRequest

from ai_agent.qgis_tools.common.expressions import (
    evaluate,
    parse_order_by,
    plain_value,
    prepared,
    sort_key,
)
from ai_agent.qgis_tools.common.values import clamp_limit, wanted_fields
from ai_agent.qgis_tools.inspect.aggregates import compute

MAX_SCAN = 50000
DEFAULT_ROW_LIMIT = 20
MAX_ROW_LIMIT = 200
MAX_GROUPS = 50
SCAN_LIMIT_MESSAGE = (
    "More than {limit} features match the condition, so an exact answer cannot be computed. "
    "Narrow the selection down with the filter parameter."
)


def run_aggregate(layer, request, context, params, aggregate: str) -> dict[str, Any]:
    expression_text = (params.get("expression") or "").strip()
    group_text = (params.get("group_by") or "").strip()
    value_expression = prepared(expression_text, "expression", context, layer) if expression_text else None
    group_expression = prepared(group_text, "group_by", context, layer) if group_text else None

    if value_expression is None and group_expression is None:
        return _bare_count(layer, request, aggregate)

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
        info["groups_note"] = f"showing the first {MAX_GROUPS} groups out of {len(groups)}"
    return info


def _bare_count(layer, request, aggregate: str) -> dict[str, Any]:
    matched = 0
    for _ in layer.getFeatures(request.setNoAttributes()):
        matched += 1
        if matched > MAX_SCAN:
            raise ValueError(SCAN_LIMIT_MESSAGE.format(limit=MAX_SCAN))
    return {"aggregate": aggregate, "matched": matched, "value": compute(aggregate, [], matched)}


def run_rows(layer, request, context, params) -> dict[str, Any]:
    order_text, ascending = parse_order_by(params.get("order_by") or "")
    order_expression = prepared(order_text, "order_by", context, layer) if order_text else None
    limit = clamp_limit(params.get("limit"), DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT)
    slots = _field_slots(layer, wanted_fields(layer, params.get("fields")))
    provider_ordered = _bound_request(request, order_text, ascending, limit, slots, layer)
    bounded = not order_text or provider_ordered

    collected = []
    for feature in layer.getFeatures(request):
        if len(collected) >= MAX_SCAN:
            raise ValueError(SCAN_LIMIT_MESSAGE.format(limit=MAX_SCAN))
        key = evaluate(order_expression, context, feature) if order_expression and not provider_ordered else None
        collected.append((key, _attributes(feature, slots)))

    if order_expression is not None and not provider_ordered:
        collected.sort(key=lambda item: sort_key(item[0]), reverse=not ascending)
    has_more = bounded and len(collected) > limit
    info: dict[str, Any] = {
        "matched": len(collected),
        "shown": min(limit, len(collected)),
        "features": [attributes for _, attributes in collected[:limit]],
    }
    if has_more:
        info["matched_is_lower_bound"] = True
        info["has_more"] = True
        info["note"] = f"More than {limit} features match; use aggregate=count for an exact total."
    if order_text:
        info["order_by"] = f"{order_text} {'ASC' if ascending else 'DESC'}"
    return info


def _bound_request(request, order_text: str, ascending: bool, limit: int, slots, layer) -> bool:
    provider_ordered = False
    if order_text:
        try:
            clause = QgsFeatureRequest.OrderByClause(order_text, ascending)
            request.setOrderBy(QgsFeatureRequest.OrderBy([clause]))
            provider_ordered = True
        except (AttributeError, TypeError, ValueError):
            provider_ordered = False
    if not order_text or provider_ordered:
        request.setLimit(limit + 1)
        if slots and not order_text:
            try:
                request.setSubsetOfAttributes([index for _, index in slots], layer.fields())
            except (AttributeError, TypeError, ValueError):
                pass
    return provider_ordered


def _build_groups(aggregate: str, groups: dict[Any, list[Any]]) -> list[dict[str, Any]]:
    ordered = sorted(groups.items(), key=lambda item: sort_key(item[0]))
    return [
        {"group": group, "count": len(items), "value": compute(aggregate, items, len(items))}
        for group, items in ordered[:MAX_GROUPS]
    ]


def _field_slots(layer, wanted: list[str] | None) -> list[tuple[str, int]]:
    try:
        names = layer.fields().names()
    except Exception:
        return []
    return [(name, index) for index, name in enumerate(names) if wanted is None or name in wanted]


def _attributes(feature, slots: list[tuple[str, int]]) -> dict[str, Any]:
    values = feature.attributes()
    return {name: plain_value(values[index]) for name, index in slots if index < len(values)}
