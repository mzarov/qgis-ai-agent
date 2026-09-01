from contextlib import suppress
from typing import Any


def describe_labeling(layer) -> dict[str, Any]:
    info: dict[str, Any] = {"enabled": _labels_enabled(layer)}
    if not info["enabled"]:
        return info
    settings = _label_settings(layer)
    if settings is None:
        return info
    field = getattr(settings, "fieldName", "")
    if field:
        info["field"] = field
    expression = _is_expression(settings)
    if expression:
        info["field_is_expression"] = True
    info.update(_text_format(settings))
    return info


def _labels_enabled(layer) -> bool:
    try:
        return bool(layer.labelsEnabled())
    except Exception:
        return False


def _label_settings(layer: Any) -> Any:
    try:
        return layer.labeling().settings()
    except Exception:
        return None


def _is_expression(settings) -> bool:
    try:
        return bool(settings.isExpression)
    except Exception:
        return False


def _text_format(settings) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        text_format = settings.format()
    except Exception:
        return info
    with suppress(Exception):
        info["font_size"] = round(float(text_format.size()), 2)
    with suppress(Exception):
        info["font"] = text_format.font().family()
    with suppress(Exception):
        info["color"] = text_format.color().name()
    return info
