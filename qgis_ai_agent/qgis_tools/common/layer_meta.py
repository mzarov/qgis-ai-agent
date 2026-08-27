import re
from typing import Any

from qgis.core import QgsMapLayer, QgsVectorLayer

SECRET_KEYS = ("password", "passwd", "pwd", "token", "api_key", "apikey", "secret")
SECRET_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(SECRET_KEYS) + r")\s*=\s*('[^']*'|\"[^\"]*\"|\S+)"
)
SECRET_PLACEHOLDER = "<hidden>"
MAX_SOURCE_CHARS = 300


def sanitize_source(source: str) -> str:
    if not source:
        return ""
    cleaned = SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={SECRET_PLACEHOLDER}", source)
    if len(cleaned) > MAX_SOURCE_CHARS:
        return cleaned[:MAX_SOURCE_CHARS] + "…"
    return cleaned


def provider_name(layer: QgsMapLayer) -> str:
    for getter in ("providerType", "dataProvider"):
        try:
            value = getattr(layer, getter)()
        except Exception:
            continue
        if isinstance(value, str):
            return value
        try:
            return value.name()
        except Exception:
            continue
    return ""


def layer_source(layer: QgsMapLayer) -> str:
    try:
        return sanitize_source(layer.source() or "")
    except Exception:
        return ""


def is_valid(layer: QgsMapLayer) -> bool:
    try:
        return bool(layer.isValid())
    except Exception:
        return True


def subset_filter(layer: QgsMapLayer) -> str:
    if not isinstance(layer, QgsVectorLayer):
        return ""
    try:
        return layer.subsetString() or ""
    except Exception:
        return ""


def selected_count(layer: QgsMapLayer) -> int | None:
    if not isinstance(layer, QgsVectorLayer):
        return None
    try:
        return int(layer.selectedFeatureCount())
    except Exception:
        return None


def layer_opacity(layer: QgsMapLayer) -> float | None:
    try:
        return round(float(layer.opacity()), 3)
    except Exception:
        return None


def describe_source(layer: QgsMapLayer) -> dict[str, Any]:
    info: dict[str, Any] = {
        "provider": provider_name(layer),
        "source": layer_source(layer),
        "is_valid": is_valid(layer),
    }
    if not info["is_valid"]:
        info["warning"] = (
            "The layer failed to load: the source is unreachable or the path is broken. "
            "Processing and styling will not work on it."
        )
    filter_expression = subset_filter(layer)
    if filter_expression:
        info["subset_filter"] = filter_expression
        info["filter_note"] = "The feature count above already reflects this filter."
    selected = selected_count(layer)
    if selected:
        info["selected_count"] = selected
    opacity = layer_opacity(layer)
    if opacity is not None and opacity < 1.0:
        info["opacity"] = opacity
    return info
