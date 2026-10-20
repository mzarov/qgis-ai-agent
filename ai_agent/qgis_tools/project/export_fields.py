from typing import Any

from qgis.core import QgsVectorLayer

from ai_agent.qgis_tools.common.layers import enum_name

FIELDS_NOTE = (
    "The shapefile could not keep some fields as they were: renamed_fields and retyped_fields name them. "
    "Tell the user; a GeoPackage keeps every name and type."
)
TYPE_FAMILIES = {
    "Int": "integer",
    "UInt": "integer",
    "LongLong": "integer",
    "ULongLong": "integer",
    "Double": "real",
    "QString": "text",
    "QDate": "date",
    "QDateTime": "datetime",
    "QTime": "time",
    "Bool": "boolean",
}


def field_changes(layer: Any, path: str) -> dict[str, Any]:
    source = list(layer.fields())
    written = list(QgsVectorLayer(path, "export check", "ogr").fields())
    if len(written) != len(source):
        return {}
    pairs = list(zip(source, written, strict=True))
    renamed = {before.name(): after.name() for before, after in pairs if before.name() != after.name()}
    retyped = {
        before.name(): f"{_family(before)} → {_family(after)}"
        for before, after in pairs
        if _family(before) != _family(after)
    }
    changes: dict[str, Any] = {}
    if renamed:
        changes["renamed_fields"] = renamed
    if retyped:
        changes["retyped_fields"] = retyped
    if changes:
        changes["fields_note"] = FIELDS_NOTE
    return changes


def _family(field: Any) -> str:
    name = enum_name(field.type())
    return TYPE_FAMILIES.get(name, name.lstrip("Q").lower())
