import json
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from ai_agent.qgis_tools.web.html_text import html_to_text
from ai_agent.qgis_tools.web.http import encoded, get_text

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/?q={query}"
RESULT_LINK = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
RESULT_SNIPPET = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
MAX_RESULTS = 8
NOTHING = "The search returned no results — try different words."
WIKIPEDIA_ENDPOINT = (
    "https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&utf8=&srlimit={limit}"
)
WIKIPEDIA_PAGE = "https://{lang}.wikipedia.org/wiki/{title}"
TAG_ONLY = re.compile(r"<[^>]+>")
WIKIPEDIA_NOTE = (
    "The general search engine was unreachable from this network, so these "
    "results are from Wikipedia only — an encyclopedia, not the whole web."
)


class SearchWebTool(BaseTool):
    name = "search_web"
    description = (
        "Search the web (DuckDuckGo) and return titles, links and snippets. "
        "Follow up with fetch_url on the promising link. For place names and "
        "coordinates prefer geocode — it answers directly."
    )
    skill = "web"
    safety = SAFETY_READ
    constraints = ["Returns up to 8 results", "A public service — one search per question, not a barrage"]
    examples = ["Find the EPSG code for Kazan", "What is the OSM tag for pharmacies?"]
    params_schema = [
        {"name": "query", "type": "string", "description": "Search words, any language", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Searching the web: {0}.").format(str(params.get("query") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query") or "").strip()
        if not query:
            raise ValueError("The query is empty.")
        try:
            html = get_text(SEARCH_ENDPOINT.format(query=encoded(query)))
            results = parse_results(html)
            note = ""
            engine = "duckduckgo"
        except ValueError:
            results = wikipedia_results(query)
            note = WIKIPEDIA_NOTE
            engine = "wikipedia"
        if not results:
            raise ValueError(NOTHING)
        answer: dict[str, Any] = {"query": query, "engine": engine, "results": results}
        if note:
            answer["note"] = note
        return answer


def parse_results(html: str) -> list[dict[str, str]]:
    links = RESULT_LINK.findall(html or "")
    snippets = [html_to_text(snippet) for snippet in RESULT_SNIPPET.findall(html or "")]
    results = []
    for index, (href, title) in enumerate(links[:MAX_RESULTS]):
        results.append(
            {
                "title": html_to_text(title),
                "url": _unwrapped(href),
                "snippet": snippets[index] if index < len(snippets) else "",
            }
        )
    return results


def _unwrapped(href: str) -> str:
    parsed = urlparse(href if "//" in href else f"https:{href}" if href.startswith("//") else href)
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
        packed = parse_qs(parsed.query).get("uddg", [""])[0]
        if packed:
            return unquote(packed)
    return href


def wikipedia_results(query: str) -> list[dict[str, str]]:
    lang = "en" if query.isascii() else "ru"
    body = get_text(WIKIPEDIA_ENDPOINT.format(lang=lang, query=encoded(query), limit=MAX_RESULTS))
    return parse_wikipedia(body, lang)


def parse_wikipedia(body: str, lang: str) -> list[dict[str, str]]:
    try:
        raw = json.loads(body or "{}")
    except ValueError:
        return []
    hits = ((raw.get("query") or {}).get("search")) or []
    results = []
    for hit in hits[:MAX_RESULTS]:
        title = str(hit.get("title") or "")
        results.append(
            {
                "title": title,
                "url": WIKIPEDIA_PAGE.format(lang=lang, title=encoded(title.replace(" ", "_"))),
                "snippet": unescape(TAG_ONLY.sub("", str(hit.get("snippet") or ""))),
            }
        )
    return results
