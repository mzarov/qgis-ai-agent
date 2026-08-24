from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.processing.utils import algorithm_brief, get_registry

DEFAULT_LIMIT = 12
MAX_LIMIT = 30
FIELD_WEIGHTS = (("name", 5), ("id", 4), ("tags", 2), ("group", 1))


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
        limit = self._resolve_limit(params.get("limit"))

        scored = [
            (score, algorithm_brief(algorithm))
            for score, algorithm in (
                (self._score(algorithm, terms), algorithm)
                for algorithm in get_registry().algorithms()
            )
            if score > 0
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "query": query,
            "total_matched": len(scored),
            "algorithms": [brief for _, brief in scored[:limit]],
        }

    @staticmethod
    def _resolve_limit(raw: Any) -> int:
        try:
            value = int(raw) if raw is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            value = DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    @classmethod
    def _score(cls, algorithm, terms: list[str]) -> int:
        if not terms:
            return 0
        haystack = cls._haystack(algorithm)
        return sum(
            weight
            for field, weight in FIELD_WEIGHTS
            for term in terms
            if term in haystack[field]
        )

    @staticmethod
    def _haystack(algorithm) -> dict[str, str]:
        try:
            tags = " ".join(algorithm.tags())
        except Exception:
            tags = ""
        return {
            "name": (algorithm.displayName() or "").lower(),
            "id": (algorithm.id() or "").lower(),
            "tags": tags.lower(),
            "group": (algorithm.group() or "").lower(),
        }
