from typing import Any

from qgis.core import QgsField, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name
from qgis_ai_agent.qgis_tools.common.values import suggest_fields

FIELD_TYPES = {
    "text": (QVariant.String, 255, 0),
    "integer": (QVariant.Int, 10, 0),
    "double": (QVariant.Double, 20, 6),
    "boolean": (QVariant.Bool, 1, 0),
    "date": (QVariant.Date, 10, 0),
}
MAX_NAME_CHARS = 63
COMMIT_FAILED = "QGIS could not commit the schema change: {reason}. The layer was rolled back."


def require_vector(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no attribute schema.")
    return layer


def field_names(layer: QgsVectorLayer) -> list[str]:
    try:
        return list(layer.fields().names())
    except Exception:
        return []


def require_field_index(layer: QgsVectorLayer, name: str) -> int:
    wanted = (name or "").strip()
    index = layer.fields().indexFromName(wanted)
    if index < 0:
        raise ValueError(
            f"Layer '{layer.name()}' has no field '{wanted}'. {suggest_fields([wanted], field_names(layer))}"
        )
    return index


def checked_new_name(layer: QgsVectorLayer, name: Any) -> str:
    wanted = str(name or "").strip()
    if not wanted:
        raise ValueError("The field needs a name.")
    if len(wanted) > MAX_NAME_CHARS:
        raise ValueError(f"'{wanted}' is longer than {MAX_NAME_CHARS} characters — most formats will truncate it.")
    if wanted in field_names(layer):
        raise ValueError(f"Layer '{layer.name()}' already has a field named '{wanted}'.")
    return wanted


def build_field(name: str, kind: Any) -> QgsField:
    wanted = str(kind or "").strip().lower()
    if wanted not in FIELD_TYPES:
        raise ValueError(f"Unknown field type '{kind}'. Available: {', '.join(sorted(FIELD_TYPES))}.")
    variant, length, precision = FIELD_TYPES[wanted]
    return QgsField(name, variant, "", length, precision)


def commit(layer: QgsVectorLayer) -> None:
    if layer.commitChanges():
        return
    reason = "; ".join(layer.commitErrors() or []) or "provider refused"
    layer.rollBack()
    raise ValueError(COMMIT_FAILED.format(reason=reason))


def start_editing(layer: QgsVectorLayer) -> None:
    if not layer.startEditing():
        raise ValueError(f"Layer '{layer.name()}' cannot be switched into editing mode.")
