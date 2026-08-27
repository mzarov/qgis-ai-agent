import difflib
from typing import Any

from qgis.core import QgsMapLayer

MAX_LISTED_FIELDS = 25
CLOSE_MATCH_CUTOFF = 0.6


def plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        if value.isNull():
            return None
    except AttributeError:
        pass
    return str(value)


def clamp_limit(raw: Any, default: int, maximum: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def wanted_fields(layer: QgsMapLayer, raw: Any) -> list[str] | None:
    if not isinstance(raw, list) or not raw:
        return None
    available = set(layer.fields().names())
    wanted = [str(name) for name in raw if str(name) in available]
    return wanted or None


def suggest_fields(unknown: list[str], available: list[str]) -> str:
    close: list[str] = []
    for name in unknown:
        close.extend(difflib.get_close_matches(name, available, n=3, cutoff=CLOSE_MATCH_CUTOFF))
    if close:
        return "Similar fields: " + ", ".join(dict.fromkeys(close)) + "."
    ordered = sorted(available)
    shown = ", ".join(ordered[:MAX_LISTED_FIELDS])
    if len(ordered) > MAX_LISTED_FIELDS:
        return (
            f"First {MAX_LISTED_FIELDS} fields: {shown}. "
            f"There are {len(ordered)} fields in total, call describe_layer for the full list."
        )
    return f"Available fields: {shown}."
