from contextlib import suppress
from typing import Any

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeatureRequest,
)

from ai_agent.qgis_tools.common.values import plain_value, suggest_fields

DESCENDING_MARKERS = ("desc", "descending")
ASCENDING_MARKERS = ("asc", "ascending")
SPECIAL_COLUMNS = {"*", "$geometry", "$id", "$area", "$length", "$perimeter", "$x", "$y"}
# An @parent aggregate references ALL_ATTRIBUTES; refusing it breaks valid expressions.
ALL_ATTRIBUTES = "#!allattributes!#"
QUOTED_EXPRESSION_HINT = (
    "A name in double quotes is a field; an expression goes without quotes — inside aggregate, for one: "
    "aggregate('schools', 'count', $id, intersects($geometry, geometry(@parent)))."
)


def build_context(layer) -> QgsExpressionContext:
    context = QgsExpressionContext()
    with suppress(Exception):
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    return context


def compile_expression(text: str, label: str, layer=None) -> QgsExpression:
    expression = QgsExpression(text)
    if expression.hasParserError():
        raise ValueError(
            f"Could not parse the expression in '{label}': {expression.parserErrorString().strip()}. "
            f"The expression was: {text}"
        )
    if layer is not None:
        check_columns(expression, layer, label, text)
    return expression


def check_columns(expression: QgsExpression, layer, label: str, text: str) -> None:
    try:
        referenced = set(expression.referencedColumns())
    except Exception:
        return
    available = set(layer.fields().names())
    skipped = SPECIAL_COLUMNS | {ALL_ATTRIBUTES}
    unknown = sorted(name for name in referenced if name and name not in skipped and name not in available)
    if not unknown:
        return
    quoted_call = any("(" in name for name in unknown)
    raise ValueError(
        f"The expression in '{label}' refers to fields that do not exist: {', '.join(unknown)}. "
        f"The expression was: {text}. {suggest_fields(unknown, sorted(available))} "
        + (
            QUOTED_EXPRESSION_HINT
            if quoted_call
            else "If this was meant as a text value, write it in single quotes: highway = 'motorway'."
        )
    )


def prepared(text: str, label: str, context: QgsExpressionContext, layer=None) -> QgsExpression:
    expression = compile_expression(text, label, layer)
    with suppress(Exception):
        expression.prepare(context)
    return expression


def evaluate(expression: QgsExpression, context: QgsExpressionContext, feature) -> Any:
    return plain_value(evaluate_raw(expression, context, feature))


def evaluate_raw(expression: QgsExpression, context: QgsExpressionContext, feature) -> Any:
    context.setFeature(feature)
    value = expression.evaluate(context)
    if expression.hasEvalError():
        raise ValueError(
            f"Could not evaluate the expression '{expression.expression()}': {expression.evalErrorString().strip()}"
        )
    return value


def build_request(filter_text: str, layer=None) -> QgsFeatureRequest:
    request = QgsFeatureRequest()
    # Without the layer's scopes $area is flat in layer units and is_selected() matches nothing.
    if layer is not None:
        request.setExpressionContext(build_context(layer))
    text = (filter_text or "").strip()
    if not text:
        return request
    compile_expression(text, "filter", layer)
    request.setFilterExpression(text)
    return request


def parse_order_by(order_by: str) -> tuple[str, bool]:
    text = (order_by or "").strip()
    if not text:
        return "", True
    parts = text.rsplit(None, 1)
    if len(parts) == 2:
        marker = parts[1].lower()
        if marker in DESCENDING_MARKERS:
            return parts[0].strip(), False
        if marker in ASCENDING_MARKERS:
            return parts[0].strip(), True
    return text, True


def sort_key(value: Any) -> tuple:
    if value is None:
        return (2, "", 0.0)
    if isinstance(value, bool):
        return (1, "bool", float(value))
    if isinstance(value, (int, float)):
        return (0, "", float(value))
    return (1, str(value).lower(), 0.0)
