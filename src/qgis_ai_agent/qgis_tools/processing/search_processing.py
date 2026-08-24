from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.processing.utils import algorithm_brief, get_registry

# Алгоритмов в QGIS больше тысячи — отдаём модели только верх выдачи.
DEFAULT_LIMIT = 12
MAX_LIMIT = 30


class SearchProcessingTool(BaseTool):
    """Поиск алгоритма обработки по описанию задачи."""
    name = "search_processing"
    description = (
        "Найти алгоритм обработки QGIS по ключевым словам "
        "(например «буфер», «пересечение», «репроекция»). "
        "Возвращает идентификаторы вида native:buffer для describe_processing."
    )
    skill = "processing"
    safety = SAFETY_READ
    capabilities = ["processing:search"]
    examples = ["Найди алгоритм построения буфера", "Чем обрезать слой по границе?"]
    constraints = []
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "Ключевые слова задачи на русском или английском",
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
        """Описание шага поиска алгоритма."""
        query = (params.get("query") or "").strip()
        return f"Ищу алгоритм: «{query}»." if query else "Ищу алгоритм обработки."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = (params.get("query") or "").strip().lower()
        if not query:
            raise ValueError("Не задан поисковый запрос.")
        limit = self._resolve_limit(params.get("limit"))

        scored: list[tuple[int, dict[str, Any]]] = []
        for algorithm in get_registry().algorithms():
            score = self._score(algorithm, query)
            if score > 0:
                scored.append((score, algorithm_brief(algorithm)))
        scored.sort(key=lambda item: item[0], reverse=True)

        return {
            "query": query,
            "total_matched": len(scored),
            "algorithms": [brief for _, brief in scored[:limit]],
        }

    @staticmethod
    def _resolve_limit(raw: Any) -> int:
        """Приводит limit к разумным границам."""
        try:
            value = int(raw) if raw is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            value = DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    @staticmethod
    def _score(algorithm, query: str) -> int:
        """Оценивает совпадение: имя и идентификатор весят больше тегов."""
        terms = [term for term in query.split() if term]
        if not terms:
            return 0
        name = (algorithm.displayName() or "").lower()
        alg_id = (algorithm.id() or "").lower()
        group = (algorithm.group() or "").lower()
        try:
            tags = " ".join(algorithm.tags()).lower()
        except Exception:
            tags = ""

        score = 0
        for term in terms:
            if term in name:
                score += 5
            if term in alg_id:
                score += 4
            if term in tags:
                score += 2
            if term in group:
                score += 1
        return score
