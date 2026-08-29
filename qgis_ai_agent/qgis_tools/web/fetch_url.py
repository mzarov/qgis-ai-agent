from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.web.html_text import html_to_text
from qgis_ai_agent.qgis_tools.web.http import checked_url, get_text

DEFAULT_CHARS = 6000
MAX_CHARS = 20000


class FetchUrlTool(BaseTool):
    name = "fetch_url"
    description = (
        "Fetch a web page and return its readable text. HTML is stripped to plain "
        "text; JSON and plain text come back as they are. Use it to read "
        "documentation, data descriptions or anything the user links to."
    )
    skill = "web"
    safety = SAFETY_READ
    constraints = ["Only http and https", "The text is truncated to max_chars"]
    examples = ["Read this page and summarise it", "What does this API doc say?"]
    params_schema = [
        {"name": "url", "type": "string", "description": "The http(s) address to fetch", "required": True},
        {
            "name": "max_chars",
            "type": "integer",
            "description": f"How much text to return, up to {MAX_CHARS}. Default {DEFAULT_CHARS}.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading {0}.").format(str(params.get("url") or "").strip() or "URL")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        url = checked_url(params.get("url"))
        limit = _limit(params.get("max_chars"))
        body = get_text(url)
        text = html_to_text(body) if "<" in body[:1000].lower() else body
        truncated = len(text) > limit
        return {
            "url": url,
            "text": text[:limit],
            "truncated": truncated,
            "note": "Raise max_chars for more." if truncated else "",
        }


def _limit(raw: Any) -> int:
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CHARS
    return max(200, min(wanted, MAX_CHARS))
