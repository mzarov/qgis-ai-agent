import json
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import EGRESS_WEB_CONTENT, SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.web.http import checked_url, get_text, safe_url_label
from qgis_ai_agent.qgis_tools.web.url_policy import bounded_text, short_text

MAX_MATCHES = 5
MAX_PLACE_CHARS = 500
NOTHING = "The geocoding service knows no such place — check the spelling or add the region."
PUBLIC_OSMF_HOST = "nominatim.openstreetmap.org"
PUBLIC_OSMF_POLICY = "https://operations.osmfoundation.org/policies/nominatim/"


class GeocodeTool(BaseTool):
    name = "geocode"
    description = (
        "Find a place with a user-provided Nominatim-compatible service: coordinates, "
        "bounding box and place type. The public OSMF Nominatim endpoint is intentionally "
        "not built in; its usage policy forbids generic LLM/no-code geocoding."
    )
    skill = "web"
    safety = SAFETY_READ
    egress = EGRESS_WEB_CONTENT
    network_access = True
    constraints = [
        "The user must explicitly provide the geocoder base URL",
        "Only a public HTTPS service is accepted",
        "The official public OSMF Nominatim endpoint is rejected",
    ]
    examples = ["Use my Nominatim server to locate Divnomorskoye"]
    params_schema = [
        {"name": "place", "type": "string", "description": "Place name, any language", "required": True},
        {
            "name": "service_url",
            "type": "string",
            "description": "Base URL of the user-approved Nominatim-compatible service",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Looking up '{0}' with {1}.").format(
            short_text(params.get("place"), MAX_PLACE_CHARS),
            safe_url_label(str(params.get("service_url") or "")),
        )

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        place = bounded_text(params.get("place"), "place name", MAX_PLACE_CHARS)
        service_url = _service_url(params.get("service_url"), resolve=False)
        checked_url(_search_url(service_url, place), resolve=False)
        return {**params, "place": place, "service_url": service_url}

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        place = bounded_text(params.get("place"), "place name", MAX_PLACE_CHARS)
        service_url = _service_url(params.get("service_url"), resolve=True)
        endpoint = _search_url(service_url, place)
        matches = parse_matches(get_text(endpoint))
        if not matches:
            raise ValueError(NOTHING)
        return {
            "place": place,
            "service": safe_url_label(service_url),
            "matches": matches,
            "attribution": "© OpenStreetMap contributors",
        }


def parse_matches(body: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(body or "[]")
    except ValueError:
        return []
    matches = []
    for item in raw[:MAX_MATCHES] if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        lat = _number(item.get("lat"))
        lon = _number(item.get("lon"))
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        box = item.get("boundingbox") or []
        entry = {
            "name": item.get("display_name", ""),
            "type": f"{item.get('category', '')}/{item.get('type', '')}",
            "lat": lat,
            "lon": lon,
        }
        if len(box) == 4:
            edges = [_number(edge) for edge in box]
            if all(edge is not None for edge in edges):
                south, north, west, east = edges
                entry["bbox"] = f"{west},{south},{east},{north}"
        matches.append(entry)
    return matches


def _service_url(raw: Any, *, resolve: bool) -> str:
    service_url = checked_url(raw, resolve=resolve)
    parsed = urlsplit(service_url)
    if (parsed.hostname or "").lower().rstrip(".") == PUBLIC_OSMF_HOST:
        raise ValueError(
            "The public OSMF Nominatim endpoint is not built into this agent. "
            f"Use a service you are authorised to use; policy: {PUBLIC_OSMF_POLICY}"
        )
    if parsed.query:
        raise ValueError("The geocoding service base URL must not contain query parameters.")
    return urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/") or "/", "", ""))


def _search_url(service_url: str, place: str) -> str:
    parsed = urlsplit(service_url)
    path = parsed.path.rstrip("/")
    if not path.endswith("/search"):
        path += "/search"
    query = urlencode({"format": "jsonv2", "limit": MAX_MATCHES, "q": place})
    return urlunsplit(("https", parsed.netloc, path, query, ""))


def _number(raw: Any) -> float | None:
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return None
