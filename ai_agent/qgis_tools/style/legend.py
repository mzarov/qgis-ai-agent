"""A restyled layer's classes as a legend the feed draws under the answer; the model never sees it.

The legend is read back from the renderer QGIS keeps after the change — the same
items the Layers panel lists — so it shows what the map shows, whatever built it.
"""

from contextlib import suppress
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.qgis_tools.base import RESULT_VISUAL_KEY

LEGEND_TYPE = "legend"
RANGES = "ranges"
CATEGORIES = "categories"
MAX_ITEMS = 12
# Renderers whose classes run in order, low to high: the feed draws them as one strip.
ORDERED_RENDERERS = frozenset({"graduatedSymbol"})


def with_legend(payload: dict[str, Any], layer: Any) -> dict[str, Any]:
    """The step's payload, with the layer's legend for the feed when it has classes to show."""
    spec = legend_spec(layer)
    return {**payload, RESULT_VISUAL_KEY: spec} if spec else payload


def legend_spec(layer: Any) -> dict[str, Any] | None:
    """Colours and labels of the layer's classes, or None when it has fewer than two."""
    items: list[dict[str, Any]] = []
    kind = CATEGORIES
    if isinstance(layer, QgsVectorLayer):
        renderer = layer.renderer()
        if renderer is None:
            return None
        with suppress(Exception):
            kind = RANGES if renderer.type() in ORDERED_RENDERERS else CATEGORIES
        if kind == RANGES:
            # The bounds as numbers: the feed words them compactly, QGIS's labels carry four decimals.
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
