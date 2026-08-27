from typing import Any

from qgis.core import QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.aggregates import AGGREGATE_FUNCTIONS
from qgis_ai_agent.qgis_tools.inspect.expressions import build_context, build_request
from qgis_ai_agent.qgis_tools.inspect.queries import DEFAULT_ROW_LIMIT, run_aggregate, run_rows
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name


class QueryLayerTool(BaseTool):
    name = "query_layer"
    description = (
        "Запросить данные слоя языком выражений QGIS: посчитать объекты по условию, "
        "агрегировать, сгруппировать, отсортировать, взять первые N. "
        "ЛЮБОЙ вопрос «сколько», «самый», «средний», «суммарный», «топ» решается этим тулом. "
        "Длина и площадь берутся прямо из геометрии выражениями $length и $area: "
        "отдельного поля с длиной в слое обычно НЕТ, и искать его не нужно."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = [
        "Слой должен существовать и быть векторным",
        "Имена полей в выражениях чувствительны к регистру",
    ]
    examples = [
        "Сколько дорог типа motorway?",
        "Топ-5 городов по населению",
        "Какая река самая длинная?",
        "Суммарная площадь озёр",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "filter",
            "type": "string",
            "description": "Условие отбора, выражение QGIS: \"highway = 'motorway'\"",
            "required": False,
        },
        {
            "name": "aggregate",
            "type": "string",
            "description": "Агрегатная функция. Без неё возвращаются сами объекты.",
            "required": False,
            "enum": list(AGGREGATE_FUNCTIONS),
        },
        {
            "name": "expression",
            "type": "string",
            "description": "Поле или выражение для агрегации: \"population\", \"$length\", \"$area\"",
            "required": False,
        },
        {
            "name": "group_by",
            "type": "string",
            "description": "Поле или выражение для группировки результата",
            "required": False,
        },
        {
            "name": "order_by",
            "type": "string",
            "description": "Сортировка объектов: \"population DESC\". Только без aggregate.",
            "required": False,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"Сколько объектов вернуть (по умолчанию {DEFAULT_ROW_LIMIT})",
            "required": False,
        },
        {
            "name": "fields",
            "type": "array",
            "items": {"type": "string"},
            "description": "Какие поля показать у объектов. По умолчанию все.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        aggregate = (params.get("aggregate") or "").strip()
        condition = (params.get("filter") or "").strip()
        action = f"считаю {aggregate}" if aggregate else "выбираю объекты"
        where = f" при условии {condition}" if condition else ""
        return f"Слой «{layer_name}»: {action}{where}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        if not isinstance(layer, QgsVectorLayer):
            raise ValueError(f"Слой «{layer.name()}» не векторный, запросить его нельзя.")

        context = build_context(layer)
        request = build_request(params.get("filter") or "", layer)
        aggregate = (params.get("aggregate") or "").strip().lower()

        result: dict[str, Any] = {"layer_name": layer.name()}
        condition = (params.get("filter") or "").strip()
        if condition:
            result["filter"] = condition
        if aggregate:
            result.update(run_aggregate(layer, request, context, params, aggregate))
        else:
            result.update(run_rows(layer, request, context, params))
        return result
