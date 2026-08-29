import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import EGRESS_WEB_CONTENT, SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.web.html_text import BLOCK_TAGS, DROP_TAGS, html_to_text, normalize_text
from qgis_ai_agent.qgis_tools.web.http import (
    RequestCancelled,
    cancellation_epoch,
    checked_url,
    get_text,
    guard_not_cancelled,
)
from qgis_ai_agent.qgis_tools.web.url_policy import bounded_text, encoded, short_text

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/?q={query}"
MAX_RESULTS = 8
MAX_QUERY_CHARS = 500
NOTHING = "The search returned no results — try different words."
WIKIPEDIA_ENDPOINT = (
    "https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&utf8=&srlimit={limit}"
)
WIKIPEDIA_PAGE = "https://{lang}.wikipedia.org/wiki/{title}"
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
    egress = EGRESS_WEB_CONTENT
    network_access = True
    constraints = ["Returns up to 8 results", "A public service — one search per question, not a barrage"]
    examples = ["Find the EPSG code for Kazan", "What is the OSM tag for pharmacies?"]
    params_schema = [
        {"name": "query", "type": "string", "description": "Search words, any language", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Searching DuckDuckGo/Wikipedia: {0}.").format(short_text(params.get("query"), MAX_QUERY_CHARS))

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        query = bounded_text(params.get("query"), "query", MAX_QUERY_CHARS)
        checked_url(SEARCH_ENDPOINT.format(query=encoded(query)), resolve=False)
        return {**params, "query": query}

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = bounded_text(params.get("query"), "query", MAX_QUERY_CHARS)
        epoch = cancellation_epoch()
        guard_not_cancelled(epoch)
        try:
            html = get_text(SEARCH_ENDPOINT.format(query=encoded(query)), epoch=epoch)
            guard_not_cancelled(epoch)
            results = parse_results(html)
            note = ""
            engine = "duckduckgo"
        except RequestCancelled:
            raise
        except ValueError:
            guard_not_cancelled(epoch)
            results = wikipedia_results(query, epoch=epoch)
            guard_not_cancelled(epoch)
            note = WIKIPEDIA_NOTE
            engine = "wikipedia"
        guard_not_cancelled(epoch)
        if not results:
            raise ValueError(NOTHING)
        answer: dict[str, Any] = {"query": query, "engine": engine, "results": results}
        if note:
            answer["note"] = note
        return answer


def parse_results(html: str) -> list[dict[str, str]]:
    parser = SearchResultParser()
    parser.feed(str(html or ""))
    parser.close()
    parser.finish()
    results = []
    for index, (href, title) in enumerate(parser.links[:MAX_RESULTS]):
        results.append(
            {
                "title": title,
                "url": _unwrapped(href),
                "snippet": parser.snippets[index] if index < len(parser.snippets) else "",
            }
        )
    return results


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.snippets: list[str] = []
        self.kind = ""
        self.href = ""
        self.chunks: list[str] = []
        self.dropped: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if self.kind and lowered == "a":
            self.finish()
        if not self.kind and lowered == "a":
            values = {name.lower(): value or "" for name, value in attrs}
            classes = set(values.get("class", "").split())
            if "result__a" in classes:
                self.kind = "link"
                self.href = values.get("href", "")
            elif "result__snippet" in classes:
                self.kind = "snippet"
        if not self.kind:
            return
        if self.dropped:
            if lowered in DROP_TAGS:
                self.dropped.append(lowered)
        elif lowered in DROP_TAGS:
            self.dropped.append(lowered)
        elif lowered in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if self.kind and not self.dropped and tag.lower() in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self.dropped:
            if lowered == self.dropped[-1]:
                self.dropped.pop()
            return
        if self.kind and lowered == "a":
            self.finish()
        elif self.kind and lowered in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self.kind and not self.dropped:
            self.chunks.append(data)

    def finish(self) -> None:
        if not self.kind:
            return
        text = normalize_text("".join(self.chunks))
        if self.kind == "link" and self.href and len(self.links) < MAX_RESULTS:
            self.links.append((self.href, text))
        elif self.kind == "snippet" and len(self.snippets) < MAX_RESULTS:
            self.snippets.append(text)
        self.kind = ""
        self.href = ""
        self.chunks = []
        self.dropped = []


def _unwrapped(href: str) -> str:
    parsed = urlparse(href if "//" in href else f"https:{href}" if href.startswith("//") else href)
    host = (parsed.hostname or "").lower()
    if (host == "duckduckgo.com" or host.endswith(".duckduckgo.com")) and parsed.path.startswith("/l/"):
        packed = parse_qs(parsed.query).get("uddg", [""])[0]
        if packed:
            return unquote(packed)
    return href


def wikipedia_results(query: str, *, epoch: int | None = None) -> list[dict[str, str]]:
    lang = "en" if query.isascii() else "ru"
    body = get_text(
        WIKIPEDIA_ENDPOINT.format(lang=lang, query=encoded(query), limit=MAX_RESULTS),
        epoch=epoch,
    )
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
                "snippet": html_to_text(str(hit.get("snippet") or "")),
            }
        )
    return results
