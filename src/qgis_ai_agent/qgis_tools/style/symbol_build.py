from typing import Any

from qgis.core import Qgis, QgsSymbol
from qgis.PyQt.QtCore import Qt

from qgis_ai_agent.qgis_tools.style.apply import base_symbol, parse_color
from qgis_ai_agent.qgis_tools.style.properties import KIND_COLOR, KIND_ENUM, StyleProperty
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
    "не применимо к геометрии слоя «{geometry}»: {listed}. "
    "Это не ошибка — остальное применено; повторять вызов не нужно."
)


def build_symbol(layer: Any, properties: dict[str, Any]) -> tuple[QgsSymbol, dict[str, Any]]:
    symbol = base_symbol(layer)
    applied: list[str] = []
    skipped: list[str] = []
    _run(symbol, SYMBOLS.targeted(properties, TARGET_SYMBOL), applied, skipped)
    _run_layers(symbol, SYMBOLS.targeted(properties, TARGET_LAYER), applied, skipped)
    return symbol, {"applied": sorted(set(applied)), "skipped": sorted(set(skipped))}


def _run_layers(
    symbol: QgsSymbol,
    pairs: list[tuple[StyleProperty, Any]],
    applied: list[str],
    skipped: list[str],
) -> None:
    if not pairs:
        return
    count = _layer_count(symbol)
    if not count:
        skipped.extend(prop.name for prop, _ in pairs)
        return
    for index in range(count):
        _run(symbol.symbolLayer(index), pairs, applied, skipped)


def _run(
    subject: Any,
    pairs: list[tuple[StyleProperty, Any]],
    applied: list[str],
    skipped: list[str],
) -> None:
    for prop, value in pairs:
        try:
            prop.apply(subject, native(prop, value))
        except (AttributeError, TypeError, ValueError):
            skipped.append(prop.name)
            continue
        applied.append(prop.name)


def native(prop: StyleProperty, value: Any) -> Any:
    if prop.kind == KIND_COLOR:
        return parse_color(value, f"Свойство «{prop.name}»")
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
