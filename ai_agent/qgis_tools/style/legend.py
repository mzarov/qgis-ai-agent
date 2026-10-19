from contextlib import suppress
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.qgis_tools.base import RESULT_VISUAL_KEY

LEGEND_TYPE = "legend"
RANGES = "ranges"
CATEGORIES = "categories"
MAX_ITEMS = 12
ORDERED_RENDERERS = frozenset({"graduatedSymbol"})


def with_legend(payload: dict[str, Any], layer: Any) -> dict[str, Any]:
    spec = legend_spec(layer)
    return {**payload, RESULT_VISUAL_KEY: spec} if spec else payload


def legend_spec(layer: Any) -> dict[str, Any] | None:
    items: list[dict[str, Any]] = []
    kind = CATEGORIES
    if isinstance(layer, QgsVectorLayer):
        renderer = layer.renderer()
        if renderer is None:
            return None
        with suppress(Exception):
            kind = RANGES if renderer.type() in ORDERED_RENDERERS else CATEGORIES
        if kind == RANGES:
            for bounds in renderer.ranges():
                colour = bounds.symbol().color().name()
                low, high = float(bounds.lowerValue()), float(bounds.upperValue())
                items.append({"color": colour, "label": str(bounds.label()), "low": low, "high": high})
        else:
            for entry in renderer.legendSymbolItems():
                symbol = entry.symbol()
                if symbol is not None:
                    items.append({"color": symbol.color().name(), "label": str(entry.label())})
    elif isinstance(layer, QgsRasterLayer):
        kind = RANGES
        for label, colour in layer.legendSymbologyItems():
            items.append({"color": colour.name(), "label": str(label)})
    if len(items) < 2:
        return None
    shown = items[:MAX_ITEMS]
    return {"type": LEGEND_TYPE, "title": layer.name(), "kind": kind, "items": shown, "more": len(items) - len(shown)}
