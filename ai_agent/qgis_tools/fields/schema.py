from contextlib import suppress
from typing import Any

from qgis.core import QgsFeatureRequest, QgsField, QgsVectorLayer
from qgis.PyQt.QtCore import QMetaType

from ai_agent.qgis_tools.common.expressions import build_context, compile_expression
from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.common.values import suggest_fields

FIELD_TYPES = {
    "text": (QMetaType.Type.QString, 255, 0),
    "integer": (QMetaType.Type.Int, 10, 0),
    "double": (QMetaType.Type.Double, 20, 6),
    "boolean": (QMetaType.Type.Bool, 1, 0),
    "date": (QMetaType.Type.QDate, 10, 0),
    "datetime": (QMetaType.Type.QDateTime, 0, 0),
}
# A virtual field is never written to a source, so it gets the widest type of
# each kind: a 64-bit integer cannot overflow on large sums.
VIRTUAL_TYPES = {
    "text": QMetaType.Type.QString,
    "integer": QMetaType.Type.LongLong,
    "double": QMetaType.Type.Double,
    "boolean": QMetaType.Type.Bool,
    "date": QMetaType.Type.QDate,
    "datetime": QMetaType.Type.QDateTime,
}
FALLBACK_VIRTUAL_TYPE = "text"
TYPE_SAMPLE_FEATURES = 20
DATE_CLASSES = {"QDate": "date", "QDateTime": "datetime"}
MAX_NAME_CHARS = 63


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


def infer_virtual_type(layer: QgsVectorLayer, expression_text: str) -> str:
    """Name the VIRTUAL_TYPES kind of the first non-NULL value the expression yields.

    A virtual field declared with the wrong type silently shows NULL (text in a
    double field), so the type follows real values; no value at all means text.
    """
    expression = compile_expression(expression_text, "expression", layer)
    context = build_context(layer)
    with suppress(Exception):
        expression.prepare(context)
    try:
        features = layer.getFeatures(QgsFeatureRequest().setLimit(TYPE_SAMPLE_FEATURES))
    except Exception:
        return FALLBACK_VIRTUAL_TYPE
    for feature in features:
        context.setFeature(feature)
        kind = ""
        with suppress(Exception):
            kind = value_type_name(expression.evaluate(context))
        if kind:
            return kind
    return FALLBACK_VIRTUAL_TYPE


def value_type_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    with suppress(Exception):
        if value.isNull():
            return ""
    return DATE_CLASSES.get(type(value).__name__, FALLBACK_VIRTUAL_TYPE)


def build_virtual_field(name: str, kind: Any) -> QgsField:
    wanted = str(kind or "").strip().lower()
    if wanted not in VIRTUAL_TYPES:
        raise ValueError(f"Unknown virtual field type '{kind}'. Available: {', '.join(sorted(VIRTUAL_TYPES))}.")
    return QgsField(name, VIRTUAL_TYPES[wanted])


def build_field(name: str, kind: Any) -> QgsField:
    wanted = str(kind or "").strip().lower()
    if wanted not in FIELD_TYPES:
        raise ValueError(f"Unknown field type '{kind}'. Available: {', '.join(sorted(FIELD_TYPES))}.")
    variant, length, precision = FIELD_TYPES[wanted]
    return QgsField(name, variant, "", length, precision)
