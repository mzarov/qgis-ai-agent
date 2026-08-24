from typing import Any

SYMBOL_KINDS = {0: "точки", 1: "линии", 2: "полигоны"}
MULTILAYER_NOTE = "описан только первый слой символа"


def symbol_info(symbol) -> dict[str, Any]:
    info: dict[str, Any] = {}
    kind = _symbol_kind(symbol)
    if kind:
        info["kind"] = kind
    try:
        info["fill_color"] = symbol.color().name()
    except Exception:
        pass
    for key, getter in (("opacity", "opacity"), ("size", "size"), ("width", "width")):
        try:
            info[key] = round(float(getattr(symbol, getter)()), 3)
        except Exception:
            continue
    info.update(_stroke_info(symbol))
    layers = _symbol_layer_count(symbol)
    if layers > 1:
        info["symbol_layers"] = layers
        info["symbol_layers_note"] = MULTILAYER_NOTE
    return info


def _symbol_kind(symbol) -> str:
    try:
        return SYMBOL_KINDS.get(int(symbol.type()), "")
    except Exception:
        return ""


def _symbol_layer_count(symbol) -> int:
    try:
        return int(symbol.symbolLayerCount())
    except Exception:
        return 0


def _stroke_info(symbol) -> dict[str, Any]:
    try:
        layer = symbol.symbolLayer(0)
    except Exception:
        return {}
    info: dict[str, Any] = {}
    try:
        info["stroke_color"] = layer.strokeColor().name()
    except Exception:
        pass
    try:
        info["stroke_width"] = round(float(layer.strokeWidth()), 3)
    except Exception:
        pass
    return info
