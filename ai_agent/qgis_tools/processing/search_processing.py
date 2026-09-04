from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.values import clamp_limit
from ai_agent.qgis_tools.processing.ranking import score
from ai_agent.qgis_tools.processing.utils import algorithm_brief, build_search_index

DEFAULT_LIMIT = 12
MAX_LIMIT = 30


class SearchProcessingTool(BaseTool):
    name = "search_processing"
    description = (
        "Find a QGIS processing algorithm by keywords. "
        "Search in English: algorithm identifiers and tags are in English. "
        "Returns identifiers such as native:buffer for describe_processing."
    )
    skill = "processing"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Find an algorithm that builds a buffer", "What clips a layer by a boundary?"]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "Keywords describing the task, preferably in English",
            "required": True,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"How many results to return (default {DEFAULT_LIMIT})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        query = (params.get("query") or "").strip()
        if not query:
            return tr("Searching for a processing algorithm.")
        return tr("Searching for an algorithm: '{0}'.").format(query)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = (params.get("query") or "").strip().lower()
        if not query:
            raise ValueError("No search query was given.")
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
