from typing import Any

SYMBOL_KINDS = {0: "точки", 1: "линии", 2: "полигоны"}
MULTILAYER_NOTE = "описан только первый слой символа"


def symbol_info(symbol) -> dict[str, Any]:
    info: dict[str, Any] = {}
    kind = _symbol_kind(symbol)
    if kind:
        info["kind"] = kind
    fill = _color_name(_call(symbol, "color"))
    if fill:
        info["fill_color"] = fill
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
    stroke = _color_name(_call(layer, "strokeColor"))
    if not stroke:
        return {}
    info: dict[str, Any] = {"stroke_color": stroke}
    try:
        info["stroke_width"] = round(float(layer.strokeWidth()), 3)
    except Exception:
        pass
    return info


def _call(owner, method):
    try:
        return getattr(owner, method)()
    except Exception:
        return None


def _color_name(color) -> str:
    try:
        name = color.name()
    except Exception:
        return ""
    try:
        if not color.isValid():
            return ""
    except AttributeError:
        pass
    return name or ""
