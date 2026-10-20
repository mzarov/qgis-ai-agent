from typing import Any

from qgis.core import Qgis, QgsSymbol
from qgis.PyQt.QtCore import Qt

from ai_agent.qgis_tools.common.colors import parse_color
from ai_agent.qgis_tools.common.properties import KIND_COLOR, KIND_ENUM, StyleProperty
from ai_agent.qgis_tools.style.apply import base_symbol
from ai_agent.qgis_tools.style.symbol_catalogue import (
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
# A simple line keeps a stroke colour it never draws: on lines it is reported, not claimed.
NOT_ON_LINES = frozenset({"stroke_color"})
NOT_APPLICABLE = (
    "does not apply to the '{geometry}' geometry of the layer: {listed}. "
    "This is not an error — the rest was applied; there is no need to repeat the call."
)


def build_symbol(layer: Any, properties: dict[str, Any]) -> tuple[QgsSymbol, dict[str, Any]]:
    symbol = base_symbol(layer)
    landed: set[str] = set()
    _run(symbol, SYMBOLS.targeted(properties, TARGET_SYMBOL), landed)
    layered = SYMBOLS.targeted(properties, TARGET_LAYER)
    if _is_line(symbol):
        layered = [(prop, value) for prop, value in layered if prop.name not in NOT_ON_LINES]
    for index in range(_layer_count(symbol)):
        _run(symbol.symbolLayer(index), layered, landed)
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


def _is_line(symbol: QgsSymbol) -> bool:
    try:
        return bool(symbol.type() == Qgis.SymbolType.Line)
    except Exception:
        return False


def _layer_count(symbol: QgsSymbol) -> int:
    try:
        return int(symbol.symbolLayerCount())
    except Exception:
        return 0
