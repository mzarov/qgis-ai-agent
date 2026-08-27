from typing import Any

from qgis.core import Qgis, QgsSymbol
from qgis.PyQt.QtCore import Qt

from qgis_ai_agent.qgis_tools.common.colors import parse_color
from qgis_ai_agent.qgis_tools.common.properties import KIND_COLOR, KIND_ENUM, StyleProperty
from qgis_ai_agent.qgis_tools.style.apply import base_symbol
from qgis_ai_agent.qgis_tools.style.symbol_catalogue import (
    BRUSH_STYLES,
    PEN_STYLES,
    SHAPES,
    SYMBOLS,
    TARGET_LAYER,
    TARGET_SYMBOL,
)

ENUM_SOURCES = {
    "shape": (SHAPES, lambda name: getattr(Qgis.MarkerShape, name)),
    "stroke_style": (PEN_STYLES, lambda name: getattr(Qt.PenStyle, name)),
    "fill_style": (BRUSH_STYLES, lambda name: getattr(Qt.BrushStyle, name)),
}
NOT_APPLICABLE = (
    "does not apply to the '{geometry}' geometry of the layer: {listed}. "
    "This is not an error — the rest was applied; there is no need to repeat the call."
)


def build_symbol(layer: Any, properties: dict[str, Any]) -> tuple[QgsSymbol, dict[str, Any]]:
    symbol = base_symbol(layer)
    landed: set[str] = set()
    _run(symbol, SYMBOLS.targeted(properties, TARGET_SYMBOL), landed)
    for index in range(_layer_count(symbol)):
        _run(symbol.symbolLayer(index), SYMBOLS.targeted(properties, TARGET_LAYER), landed)
    asked = [key for key in properties if key in SYMBOLS.by_name]
    return symbol, {
        "applied": sorted(key for key in asked if key in landed),
        "skipped": sorted(key for key in asked if key not in landed),
    }


def _run(subject: Any, pairs: list[tuple[StyleProperty, Any]], landed: set[str]) -> None:
    for prop, value in pairs:
        try:
            prop.apply(subject, native(prop, value))
        except (AttributeError, TypeError):
            continue
        landed.add(prop.name)


def native(prop: StyleProperty, value: Any) -> Any:
    if prop.kind == KIND_COLOR:
        return parse_color(value, f"Property '{prop.name}'")
    if prop.kind == KIND_ENUM:
        mapping, resolve = ENUM_SOURCES[prop.name]
        return resolve(mapping[value])
    return value


def note_for(skipped: list[str], geometry: str) -> str:
    if not skipped:
        return ""
    return NOT_APPLICABLE.format(geometry=geometry, listed=", ".join(skipped))


def _layer_count(symbol: QgsSymbol) -> int:
    try:
        return int(symbol.symbolLayerCount())
    except Exception:
        return 0
