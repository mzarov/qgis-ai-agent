from typing import Any

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeatureRequest,
)

DESCENDING_MARKERS = ("desc", "descending")
ASCENDING_MARKERS = ("asc", "ascending")
SPECIAL_COLUMNS = {"*", "$geometry", "$id", "$area", "$length", "$perimeter", "$x", "$y"}


def build_context(layer) -> QgsExpressionContext:
    context = QgsExpressionContext()
    try:
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    except Exception:
        pass
    return context


def compile_expression(text: str, label: str, layer=None) -> QgsExpression:
    expression = QgsExpression(text)
    if expression.hasParserError():
        raise ValueError(
            f"Ошибка разбора выражения в «{label}»: {expression.parserErrorString().strip()}. "
            f"Выражение было: {text}"
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
    unknown = sorted(
        name for name in referenced
        if name and name not in SPECIAL_COLUMNS and name not in available
    )
    if not unknown:
        return
    raise ValueError(
        f"В выражении «{label}» нет таких полей: {', '.join(unknown)}. "
        f"Выражение было: {text}. Доступные поля: {', '.join(sorted(available))}. "
        "Текстовые значения пишутся в одинарных кавычках: highway = 'motorway'."
    )


def prepared(text: str, label: str, context: QgsExpressionContext, layer=None) -> QgsExpression:
    expression = compile_expression(text, label, layer)
    try:
        expression.prepare(context)
    except Exception:
        pass
    return expression


def evaluate(expression: QgsExpression, context: QgsExpressionContext, feature) -> Any:
    context.setFeature(feature)
    value = expression.evaluate(context)
    if expression.hasEvalError():
        raise ValueError(
            f"Ошибка вычисления выражения «{expression.expression()}»: "
            f"{expression.evalErrorString().strip()}"
        )
    return plain_value(value)


def build_request(filter_text: str, layer=None) -> QgsFeatureRequest:
    request = QgsFeatureRequest()
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


def plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        if value.isNull():
            return None
    except AttributeError:
        pass
    return str(value)


def sort_key(value: Any) -> tuple:
    if value is None:
        return (2, "", 0.0)
    if isinstance(value, bool):
        return (1, "bool", float(value))
    if isinstance(value, (int, float)):
        return (0, "", float(value))
    return (1, str(value).lower(), 0.0)
