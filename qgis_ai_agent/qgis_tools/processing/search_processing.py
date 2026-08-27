from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.values import clamp_limit
from qgis_ai_agent.qgis_tools.processing.ranking import score
from qgis_ai_agent.qgis_tools.processing.utils import algorithm_brief, build_search_index

DEFAULT_LIMIT = 12
MAX_LIMIT = 30


class SearchProcessingTool(BaseTool):
    name = "search_processing"
    description = (
        "Найти алгоритм обработки QGIS по ключевым словам. "
        "Ищите по-английски: идентификаторы и теги алгоритмов английские. "
        "Возвращает идентификаторы вида native:buffer для describe_processing."
    )
    skill = "processing"
    safety = SAFETY_READ
    examples = ["Найди алгоритм построения буфера", "Чем обрезать слой по границе?"]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "Ключевые слова задачи, предпочтительно по-английски",
            "required": True,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"Сколько результатов вернуть (по умолчанию {DEFAULT_LIMIT})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        query = (params.get("query") or "").strip()
        return f"Ищу алгоритм: «{query}»." if query else "Ищу алгоритм обработки."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = (params.get("query") or "").strip().lower()
        if not query:
            raise ValueError("Не задан поисковый запрос.")
        terms = query.split()
        limit = clamp_limit(params.get("limit"), DEFAULT_LIMIT, MAX_LIMIT)

        scored = []
        for algorithm, haystack in build_search_index():
            weight = score(haystack, terms, query)
            if weight > 0:
                scored.append((weight, algorithm))
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "query": query,
            "total_matched": len(scored),
            "algorithms": [algorithm_brief(algorithm) for _, algorithm in scored[:limit]],
        }
