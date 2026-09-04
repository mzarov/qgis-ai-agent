from collections.abc import Iterable
from typing import Any


def validate_parameters(params: dict[str, Any], schema: Iterable[dict[str, Any]]) -> None:
    if not isinstance(params, dict):
        raise ValueError("Tool arguments must be an object of key-value pairs.")
    for parameter in schema:
        name = parameter.get("name")
        if not name or name not in params or params[name] is None:
            continue
        kind = parameter.get("type", "string")
        if not _matches_type(params[name], kind):
            raise ValueError(f"Parameter '{name}' must be a {kind}.")


def _matches_type(value: Any, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, (list, tuple))
    if kind == "boolean":
        return isinstance(value, bool)
    if kind in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return False
        try:
            int(value) if kind == "integer" else float(value)
        except (TypeError, ValueError, OverflowError):
            return False
    return True
