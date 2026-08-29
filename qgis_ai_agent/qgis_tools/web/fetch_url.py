from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import EGRESS_WEB_CONTENT, SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.web.html_text import html_to_text
from qgis_ai_agent.qgis_tools.web.http import checked_url, confirmation_url_label, get_document, safe_url_label

DEFAULT_CHARS = 2800
MAX_CHARS = 3000


class FetchUrlTool(BaseTool):
    name = "fetch_url"
    description = (
        "Fetch a web page and return its readable text. HTML is stripped to plain "
        "text; JSON and plain text come back as they are. Use it to read "
        "documentation, data descriptions or anything the user links to."
    )
    skill = "web"
    safety = SAFETY_READ
    egress = EGRESS_WEB_CONTENT
    network_access = True
    constraints = [
        "Only public HTTPS addresses",
        "Credentials, signed URLs and private network addresses are rejected",
        "The text is returned in pages; use next_offset to continue",
    ]
    examples = ["Read this page and summarise it", "What does this API doc say?"]
    params_schema = [
        {"name": "url", "type": "string", "description": "The http(s) address to fetch", "required": True},
        {
            "name": "max_chars",
            "type": "integer",
            "description": f"How much text to return, up to {MAX_CHARS}. Default {DEFAULT_CHARS}.",
            "required": False,
        },
        {
            "name": "offset",
            "type": "integer",
            "description": "Character offset from a previous result's next_offset. Default 0.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading {0}.").format(confirmation_url_label(str(params.get("url") or "")))

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(params)
        prepared["url"] = checked_url(params.get("url"), resolve=False)
        prepared["max_chars"] = _limit(params.get("max_chars"))
        prepared["offset"] = _offset(params.get("offset"))
        return prepared

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        url = checked_url(params.get("url"))
        limit = _limit(params.get("max_chars"))
        offset = _offset(params.get("offset"))
        body, content_type = get_document(url)
        html = content_type in {"text/html", "application/xhtml+xml"}
        text = html_to_text(body) if html or body.lstrip("\ufeff \t\r\n").startswith("<") else body
        end = min(len(text), offset + limit)
        page = text[offset:end]
        has_more = end < len(text)
        return {
            "url": safe_url_label(url),
            "text": page,
            "offset": offset,
            "next_offset": end if has_more else None,
            "total_chars": len(text),
            "note": "Fetch the same URL with next_offset as offset for more." if has_more else "",
        }


def _limit(raw: Any) -> int:
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CHARS
    return max(200, min(wanted, MAX_CHARS))


def _offset(raw: Any) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0
