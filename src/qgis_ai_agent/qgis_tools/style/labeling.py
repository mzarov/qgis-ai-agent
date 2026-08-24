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


def _label_settings(layer):
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
    try:
        info["font_size"] = round(float(text_format.size()), 2)
    except Exception:
        pass
    try:
        info["font"] = text_format.font().family()
    except Exception:
        pass
    try:
        info["color"] = text_format.color().name()
    except Exception:
        pass
    return info
