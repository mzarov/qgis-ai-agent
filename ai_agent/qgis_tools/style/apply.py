from contextlib import suppress
from typing import Any

from qgis.core import QgsStyle, QgsSymbol, QgsVectorLayer
from qgis.PyQt.QtGui import QColor

from ai_agent.qgis_tools.common.layers import find_layer_by_name
from ai_agent.qgis_tools.common.values import suggest_fields

RAMPS_SHOWN = 24


def require_vector_layer(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer_name}' is not a vector layer. Symbol styling applies to vector layers only.")
    return layer


def require_field(layer: QgsVectorLayer, field_name: str) -> str:
    names = field_names(layer)
    if field_name in names:
        return field_name
    raise ValueError(f"Layer '{layer.name()}' has no field '{field_name}'. {suggest_fields([field_name], names)}")


def field_names(layer: QgsVectorLayer) -> list[str]:
    try:
        return [field.name() for field in layer.fields()]
    except Exception:
        return []


def resolve_ramp(name: str, fallbacks: tuple[str, ...] = ()) -> Any:
    style = QgsStyle.defaultStyle()
    available = sorted(style.colorRampNames())
    wanted = (name or "").strip()
    if wanted:
        if wanted in available:
            return style.colorRamp(wanted)
        raise ValueError(f"QGIS has no colour ramp called '{wanted}'. {describe_ramps(available)}")
    for candidate in fallbacks:
        if candidate in available:
            return style.colorRamp(candidate)
    if available:
        return style.colorRamp(available[0])
    raise ValueError("The QGIS library holds no colour ramps at all — pass the colours through colors instead.")


def describe_ramps(available: list[str]) -> str:
    if not available:
        return "The colour ramp library is empty — pass a list of colours instead of a ramp."
    shown = ", ".join(available[:RAMPS_SHOWN])
    if len(available) > RAMPS_SHOWN:
        return f"Available colour ramps (first {RAMPS_SHOWN} of {len(available)}): {shown}."
    return f"Available colour ramps: {shown}."


def base_symbol(layer: QgsVectorLayer) -> QgsSymbol:
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    if symbol is None:
        raise ValueError(f"Could not build a symbol for layer '{layer.name()}'.")
    return symbol


def coloured_symbol(layer: QgsVectorLayer, color: QColor) -> QgsSymbol:
    symbol = base_symbol(layer)
    symbol.setColor(color)
    return symbol


def refresh(layer: QgsVectorLayer) -> None:
    with suppress(Exception):
        layer.triggerRepaint()
    with suppress(Exception):
        from qgis.utils import iface

        iface.layerTreeView().refreshLayerSymbology(layer.id())
