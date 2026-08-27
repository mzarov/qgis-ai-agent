from typing import Any

from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.values import plain_value
from qgis_ai_agent.qgis_tools.style.apply import (
    coloured_symbol,
    parse_color,
    refresh,
    require_field,
    require_vector_layer,
    resolve_ramp,
)

MAX_CATEGORIES = 60
DEFAULT_RAMPS = ("Set2", "Spectral", "Paired", "Viridis")


class SetCategoriesTool(BaseTool):
    name = "set_categories"
    description = (
        "Раскрасить слой по категориям: каждому значению поля — свой цвет. "
        "Цвета берутся из палитры QGIS или задаются списком. Заменяет оформление слоя."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "Поле должно существовать в слое",
        "Либо палитра, либо список цветов — что-то одно",
    ]
    examples = ["Раскрась дороги по типу", "Города по региону, палитра Set2"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "field",
            "type": "string",
            "description": "Поле, по значениям которого делятся категории",
            "required": True,
        },
        {
            "name": "ramp",
            "type": "string",
            "description": (
                "Имя палитры QGIS, например Spectral или Set2. Без неё берётся разумная "
                "по умолчанию; неизвестное имя вернёт список доступных."
            ),
            "required": False,
        },
        {
            "name": "colors",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Цвета по одному на категорию, в порядке значений. Используйте, "
                "когда нужны конкретные цвета, а не палитра."
            ),
            "required": False,
        },
        {
            "name": "values",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Какие значения поля показать. По умолчанию все уникальные значения слоя."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = require_field(layer, (params.get("field") or "").strip())
        values = _wanted_values(layer, field, params.get("values"))
        if not values:
            raise ValueError(f"В поле «{field}» слоя «{layer.name()}» нет значений для категорий.")
        if len(values) > MAX_CATEGORIES:
            raise ValueError(
                f"В поле «{field}» {len(values)} разных значений — это больше {MAX_CATEGORIES}. "
                "Для числовых данных используйте set_graduated, иначе сузьте список values."
            )
        colors = params.get("colors") or []
        if colors and len(colors) != len(values):
            raise ValueError(
                f"Цветов {len(colors)}, а категорий {len(values)}. Дайте цвет каждой "
                "категории или укажите палитру вместо списка."
            )
        for color in colors:
            parse_color(color, "Цвет категории")
        if not colors:
            resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS)
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["field"] = field
        prepared["values"] = values
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Раскрашиваю «{layer_name}» по полю «{params.get('field', '')}»."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = params.get("field") or ""
        values = params.get("values") or _wanted_values(layer, field, None)
        colors = _colours_for(values, params.get("colors"), params.get("ramp"))
        categories = [
            QgsRendererCategory(value, coloured_symbol(layer, colour), str(value))
            for value, colour in zip(values, colors)
        ]
        layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
        refresh(layer)
        return {
            "layer": layer.name(),
            "renderer": "categorizedSymbol",
            "class_attribute": field,
            "class_count": len(categories),
        }


def _wanted_values(layer: Any, field: str, requested: Any) -> list[Any]:
    if requested:
        return list(requested)
    index = layer.fields().indexFromName(field)
    if index < 0:
        return []
    return sorted(
        (plain_value(value) for value in layer.uniqueValues(index)),
        key=lambda item: (item is None, str(item)),
    )


def _colours_for(values: list[Any], colors: Any, ramp_name: Any) -> list[Any]:
    if colors:
        return [parse_color(colour, "Цвет категории") for colour in colors]
    ramp = resolve_ramp(ramp_name or "", DEFAULT_RAMPS)
    total = max(1, len(values) - 1)
    return [ramp.color(index / total) for index in range(len(values))]
