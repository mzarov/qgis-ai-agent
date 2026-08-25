from typing import Any

SYMBOL_KINDS = {0: "точки", 1: "линии", 2: "полигоны"}
MAX_SYMBOL_LAYERS = 6
LAYER_MEASURES = (("width", "width"), ("size", "size"))
OPTIONAL_MEASURES = (("offset", "offset"),)


def symbol_info(symbol) -> dict[str, Any]:
    info: dict[str, Any] = {}
    kind = _symbol_kind(symbol)
    if kind:
        info["kind"] = kind
    color = _color_name(_call(symbol, "color"))
    if color:
        info["color"] = color
    for key, getter in (("opacity", "opacity"), ("size", "size"), ("width", "width")):
        value = _number(_call(symbol, getter))
        if value is not None:
            info[key] = value
    layers = _describe_layers(symbol)
    if len(layers) > 1:
        info["layers"] = layers
        info["layers_note"] = (
            "символ собран из нескольких слоёв, они рисуются снизу вверх: "
            "слой 0 под слоем 1 и так далее"
        )
    elif layers:
        info.update({key: value for key, value in layers[0].items() if key.startswith("stroke")})
    return info


def _describe_layers(symbol) -> list[dict[str, Any]]:
    count = _number(_call(symbol, "symbolLayerCount"))
    if not count:
        return []
    result = []
    for index in range(min(int(count), MAX_SYMBOL_LAYERS)):
        layer = _call(symbol, "symbolLayer", index)
        if layer is None:
            continue
        result.append(_describe_layer(index, layer))
    return result


def _describe_layer(index: int, layer) -> dict[str, Any]:
    info: dict[str, Any] = {"index": index}
    layer_type = _call(layer, "layerType")
    if isinstance(layer_type, str) and layer_type:
        info["type"] = layer_type
    color = _color_name(_call(layer, "color"))
    if color:
        info["color"] = color
    for key, getter in LAYER_MEASURES:
        value = _number(_call(layer, getter))
        if value is not None:
            info[key] = value
    for key, getter in OPTIONAL_MEASURES:
        value = _number(_call(layer, getter))
        if value:
            info[key] = value
    stroke = _color_name(_call(layer, "strokeColor"))
    if stroke:
        info["stroke_color"] = stroke
        stroke_width = _number(_call(layer, "strokeWidth"))
        if stroke_width is not None:
            info["stroke_width"] = stroke_width
    return info


def _symbol_kind(symbol) -> str:
    try:
        return SYMBOL_KINDS.get(int(symbol.type()), "")
    except Exception:
        return ""


def _call(owner, method, *args):
    try:
        return getattr(owner, method)(*args)
    except Exception:
        return None


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _color_name(color) -> str:
    try:
        name = color.name()
    except Exception:
        return ""
    if not isinstance(name, str):
        return ""
    try:
        if not color.isValid():
            return ""
    except AttributeError:
        pass
    return name
