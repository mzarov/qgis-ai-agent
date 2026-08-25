from typing import Any

from qgis.core import QgsSingleSymbolRenderer

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.style.apply import (
    coloured_symbol,
    parse_color,
    refresh,
    require_vector_layer,
)

MAX_STROKE_WIDTH = 20.0
MAX_SIZE = 100.0


class SetSymbolTool(BaseTool):
    name = "set_symbol"
    description = (
        "Перекрасить слой одним символом: цвет заливки, цвет и толщина обводки, "
        "размер точек или толщина линий. Заменяет текущее оформление слоя."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "Слой должен существовать и быть векторным",
        "Цвета задаются как #rrggbb или английским именем",
    ]
    examples = ["Сделай реки синими", "Дороги — тонкие серые линии"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте (см. list_layers)",
            "required": True,
        },
        {
            "name": "color",
            "type": "string",
            "description": "Основной цвет: #1f78b4 или steelblue",
            "required": True,
        },
        {
            "name": "stroke_color",
            "type": "string",
            "description": "Цвет обводки. Не указывать, если обводка не нужна.",
            "required": False,
        },
        {
            "name": "stroke_width",
            "type": "number",
            "description": "Толщина обводки в миллиметрах, например 0.4",
            "required": False,
        },
        {
            "name": "size",
            "type": "number",
            "description": (
                "Размер точки или толщина линии в миллиметрах. Для полигонов не "
                "применяется."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        parse_color(params.get("color"), "Цвет")
        if params.get("stroke_color"):
            parse_color(params.get("stroke_color"), "Цвет обводки")
        for key, limit in (("stroke_width", MAX_STROKE_WIDTH), ("size", MAX_SIZE)):
            if params.get(key) is not None:
                prepared[key] = _positive(params.get(key), key, limit)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Перекрашиваю слой «{layer_name}» в {params.get('color', '')}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        symbol = coloured_symbol(layer, parse_color(params.get("color"), "Цвет"))
        applied = _tune(symbol, params)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        refresh(layer)
        return {"layer": layer.name(), "renderer": "singleSymbol", "applied": applied}


def _tune(symbol: Any, params: dict[str, Any]) -> dict[str, Any]:
    applied: dict[str, Any] = {"color": params.get("color")}
    size = params.get("size")
    if size is not None:
        for setter in ("setSize", "setWidth"):
            if _call(symbol, setter, float(size)):
                applied["size"] = float(size)
                break
    for index in range(_layer_count(symbol)):
        layer = symbol.symbolLayer(index)
        if params.get("stroke_color") and _call(
            layer, "setStrokeColor", parse_color(params["stroke_color"], "Цвет обводки")
        ):
            applied["stroke_color"] = params["stroke_color"]
        if params.get("stroke_width") is not None and _call(
            layer, "setStrokeWidth", float(params["stroke_width"])
        ):
            applied["stroke_width"] = float(params["stroke_width"])
    return applied


def _layer_count(symbol: Any) -> int:
    try:
        return int(symbol.symbolLayerCount())
    except Exception:
        return 0


def _call(target: Any, method: str, value: Any) -> bool:
    setter = getattr(target, method, None)
    if setter is None:
        return False
    try:
        setter(value)
    except Exception:
        return False
    return True


def _positive(value: Any, key: str, limit: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Параметр {key} задаётся числом в миллиметрах, например 0.6.")
    if number <= 0 or number > limit:
        raise ValueError(f"Параметр {key} должен быть больше 0 и не больше {limit:g} мм.")
    return number
