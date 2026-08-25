from typing import Any

from qgis.core import QgsSingleSymbolRenderer

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import geometry_type_name
from qgis_ai_agent.qgis_tools.style.apply import refresh, require_vector_layer
from qgis_ai_agent.qgis_tools.common.bag import properties_of, shown
from qgis_ai_agent.qgis_tools.style.symbol_build import build_symbol, note_for
from qgis_ai_agent.qgis_tools.style.symbol_catalogue import SYMBOLS


class SetSymbolTool(BaseTool):
    name = "set_symbol"
    description = (
        "Оформить слой одним символом: цвет, прозрачность, размер точки или "
        "толщина линии, обводка и её штрих, форма значка, штриховка заливки. "
        "Полный список свойств отдаёт describe_style_options. Заменяет "
        "текущее оформление слоя."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "Слой должен существовать и быть векторным",
        "Все свойства идут одним вызовом, а не несколькими",
    ]
    examples = [
        "Сделай реки синими",
        "Дороги — тонкие серые пунктирные линии",
        "Города квадратными значками с белой обводкой",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "properties",
            "type": "object",
            "description": (
                "Свойства символа парами ключ-значение, например "
                '{"color": "#1f78b4", "stroke_color": "white", "size": 2}. '
                "Имена и допустимые значения — describe_style_options "
                'с kind="symbol". Незнакомый ключ вернёт подсказку.'
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = SYMBOLS.coerce_all(properties_of(params, SYMBOLS.subject))
        if not properties:
            raise ValueError(
                "Не указано ни одного свойства символа. Список доступных — "
                'describe_style_options с kind="symbol".'
            )
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["properties"] = properties
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        try:
            properties = properties_of(params, SYMBOLS.subject)
        except ValueError:
            return f"Оформляю слой «{layer_name}»."
        return f"Оформляю «{layer_name}»: {shown(properties, SYMBOLS)}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = SYMBOLS.coerce_all(properties_of(params, SYMBOLS.subject))
        symbol, outcome = build_symbol(layer, properties)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        refresh(layer)
        result: dict[str, Any] = {
            "layer": layer.name(),
            "renderer": "singleSymbol",
            "applied": outcome["applied"],
        }
        note = note_for(outcome["skipped"], geometry_type_name(layer))
        if note:
            result["skipped"] = outcome["skipped"]
            result["skipped_note"] = note
        return result
