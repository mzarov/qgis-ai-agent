"""Attribute values of drawn features: the schema of a new layer and checks against an existing one."""

import datetime
from contextlib import suppress
from typing import Any

from qgis.core import QgsField, QgsFields, QgsVectorLayer
from qgis.PyQt.QtCore import QMetaType

from ai_agent.qgis_tools.common.values import suggest_fields

TEXT = "text"
INTEGER = "integer"
DOUBLE = "double"
BOOLEAN = "boolean"
DATE = "date"
FIELD_TYPES = (TEXT, INTEGER, DOUBLE, BOOLEAN, DATE)
MAX_FIELD_NAME = 63
MAX_FIELDS = 100
TRUE_WORDS = frozenset({"true", "yes", "1"})
FALSE_WORDS = frozenset({"false", "no", "0"})


def checked_attributes(raw: Any, position: int) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f'features[{position}].attributes must be an object such as {{"name": "Town hall"}}.')
    for name, value in raw.items():
        if isinstance(value, (dict, list, tuple)):
            raise ValueError(
                f"features[{position}].attributes.{name} must be a plain value, not {type(value).__name__}."
            )
    return dict(raw)


def new_layer_schema(raw_fields: Any, rows: list[dict[str, Any]]) -> dict[str, str]:
    """Field name → type for a new layer: the declared fields, then any other names the values use."""
    if raw_fields is not None and not isinstance(raw_fields, dict):
        raise ValueError(f'fields must be an object of name → type, e.g. {{"name": "{TEXT}", "height": "{DOUBLE}"}}.')
    schema: dict[str, str] = {}
    for name, kind in (raw_fields or {}).items():
        schema[_checked_name(name, schema)] = _checked_type(name, kind)
    for row in rows:
        for name in row:
            if name not in schema:
                schema[_checked_name(name, schema)] = _inferred_type([other.get(name) for other in rows])
    if len(schema) > MAX_FIELDS:
        raise ValueError(f"A new layer takes at most {MAX_FIELDS} fields.")
    return schema


def coerced_rows(schema: dict[str, str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Values converted to the declared types, so a mismatch fails before Apply."""
    return [{name: _coerced(name, schema[name], value) for name, value in row.items()} for row in rows]


def qgs_fields(schema: dict[str, str]) -> QgsFields:
    types = {
        TEXT: QMetaType.Type.QString,
        INTEGER: QMetaType.Type.LongLong,
        DOUBLE: QMetaType.Type.Double,
        BOOLEAN: QMetaType.Type.Bool,
        DATE: QMetaType.Type.QDate,
    }
    fields = QgsFields()
    for name, kind in schema.items():
        fields.append(QgsField(name, types[kind]))
    return fields


def check_existing_fields(layer: QgsVectorLayer, rows: list[dict[str, Any]]) -> None:
    """Refuse unknown field names and values the layer's fields cannot hold."""
    names = list(layer.fields().names())
    unknown = sorted({name for row in rows for name in row if name not in names})
    if unknown:
        raise ValueError(
            f"Layer '{layer.name()}' has no field(s) {', '.join(unknown)}. {suggest_fields(unknown, names)} "
            "Add a field with the fields skill first, or leave the value out."
        )
    for row in rows:
        for name, value in row.items():
            _check_convertible(layer, name, value)


def _checked_name(raw: Any, taken: dict[str, str]) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValueError("A field name is empty.")
    if len(name) > MAX_FIELD_NAME:
        raise ValueError(f"Field name '{name[:20]}…' is longer than {MAX_FIELD_NAME} characters.")
    if name.casefold() in {other.casefold() for other in taken}:
        raise ValueError(f"Field '{name}' is given twice (field names ignore case).")
    return name


def _checked_type(name: Any, raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in FIELD_TYPES:
        raise ValueError(f"Field '{name}' has unknown type '{raw}'. Available: {', '.join(FIELD_TYPES)}.")
    return kind


def _inferred_type(values: list[Any]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return TEXT
    if all(isinstance(value, bool) for value in present):
        return BOOLEAN
    if all(isinstance(value, int) and not isinstance(value, bool) for value in present):
        return INTEGER
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present):
        return DOUBLE
    return TEXT


def _coerced(name: str, kind: str, value: Any) -> Any:
    if value is None:
        return None
    try:
        return _convert(kind, value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            f"Value {value!r} does not fit field '{name}' ({kind}). Give a {kind} value, or null to leave it empty."
        ) from None


def _convert(kind: str, value: Any) -> Any:
    if kind == TEXT:
        return str(value)
    if kind == BOOLEAN:
        return _boolean(value)
    if kind == DATE:
        return datetime.date.fromisoformat(str(value)).isoformat()
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number")
    number = float(value)
    if kind == DOUBLE:
        return number
    if not number.is_integer():
        raise ValueError("not a whole number")
    return int(number)


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    word = str(value).strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError("not a boolean")


def _check_convertible(layer: QgsVectorLayer, name: str, value: Any) -> None:
    try:
        field = layer.fields().field(name)
        convert = field.convertCompatible
    except Exception:
        return
    try:
        convert(value)
    except ValueError as err:
        kind = ""
        with suppress(Exception):
            kind = f" ({field.typeName()})" if field.typeName() else ""
        raise ValueError(
            f"Value {value!r} does not fit field '{name}'{kind} of layer '{layer.name()}': {err}. "
            "Give a value of the field's type, or null to leave it empty."
        ) from None
