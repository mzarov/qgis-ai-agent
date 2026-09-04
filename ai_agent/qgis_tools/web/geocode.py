import json
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from ai_agent.config.geocoder import (
    GEOCODER_NOMINATIM,
    GEOCODER_PHOTON,
    get_provider,
    get_url,
    validated_service_url,
)
from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_WEB_CONTENT, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.web.http import checked_url, get_text, safe_url_label
from ai_agent.qgis_tools.web.url_policy import bounded_text, short_text

MAX_MATCHES = 5
MAX_PLACE_CHARS = 500
NOTHING = "The geocoding service knows no such place — check the spelling or add the region."


class GeocodeTool(BaseTool):
    name = "geocode"
    description = (
        "Find a place with the geocoder selected in AI Agent Settings: coordinates, "
        "bounding box and place type. Available choices are the Photon fair-use preset "
        "and a custom Nominatim-compatible service."
    )
    skill = "web"
    safety = SAFETY_READ
    external_effect = False
    egress = EGRESS_WEB_CONTENT
    network_access = True
    constraints = [
        "The geocoder destination comes only from plugin settings",
        "Only a public HTTPS service is accepted",
        "The official public OSMF Nominatim endpoint is rejected",
    ]
    examples = ["Locate Divnomorskoye"]
    params_schema = [
        {"name": "place", "type": "string", "description": "Place name, any language", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        try:
            _, service_url = _configuration(params, resolve=False)
        except ValueError:
            service_url = ""
        return tr("Looking up '{0}' with {1}.").format(
            short_text(params.get("place"), MAX_PLACE_CHARS),
            safe_url_label(service_url),
        )

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        place = bounded_text(params.get("place"), "place name", MAX_PLACE_CHARS)
        provider, service_url = _configuration({}, resolve=False)
        checked_url(_search_url(service_url, place, provider), resolve=False)
        return {"place": place, "_geocoder_provider": provider, "_geocoder_url": service_url}

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        place = bounded_text(params.get("place"), "place name", MAX_PLACE_CHARS)
        provider, service_url = _configuration(params, resolve=True)
        endpoint = _search_url(service_url, place, provider)
        matches = parse_matches(get_text(endpoint), provider)
        if not matches:
            raise ValueError(NOTHING)
        return {
            "place": place,
            "service": safe_url_label(service_url),
            "matches": matches,
            "attribution": _attribution(provider),
        }


def parse_matches(body: str, provider: str = GEOCODER_NOMINATIM) -> list[dict[str, Any]]:
    try:
        raw = json.loads(body or "[]")
    except ValueError:
        return []
    if provider == GEOCODER_PHOTON:
        return _photon_matches(raw)
    return _nominatim_matches(raw)


def _nominatim_matches(raw: Any) -> list[dict[str, Any]]:
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


def _search_url(service_url: str, place: str, provider: str) -> str:
    parsed = urlsplit(service_url)
    path = parsed.path.rstrip("/")
    if provider == GEOCODER_PHOTON:
        if not path.endswith("/api"):
            path += "/api"
        query = urlencode({"limit": MAX_MATCHES, "q": place})
    else:
        if not path.endswith("/search"):
            path += "/search"
        query = urlencode({"format": "jsonv2", "limit": MAX_MATCHES, "q": place})
    return urlunsplit(("https", parsed.netloc, path, query, ""))


def _configuration(params: dict[str, Any], *, resolve: bool) -> tuple[str, str]:
    provider = str(params.get("_geocoder_provider") or get_provider())
    raw_url = params.get("_geocoder_url") or get_url()
    if provider not in {GEOCODER_PHOTON, GEOCODER_NOMINATIM}:
        raise ValueError("Choose Photon or Custom Nominatim in AI Agent Settings first.")
    if not raw_url:
        raise ValueError("Enter a custom Nominatim URL in AI Agent Settings first.")
    service_url = validated_service_url(raw_url)
    return provider, checked_url(service_url, resolve=resolve)


def _photon_matches(raw: Any) -> list[dict[str, Any]]:
    features = raw.get("features", []) if isinstance(raw, dict) else []
    matches = []
    for feature in features[:MAX_MATCHES] if isinstance(features, list) else []:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            continue
        lon, lat = _number(coordinates[0]), _number(coordinates[1])
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        entry = {
            "name": _photon_name(properties),
            "type": f"{properties.get('osm_key', '')}/{properties.get('osm_value', '')}",
            "lat": lat,
            "lon": lon,
        }
        extent = properties.get("extent") or []
        if len(extent) == 4:
            edges = [_number(edge) for edge in extent]
            if all(edge is not None for edge in edges):
                west, south, east, north = edges
                entry["bbox"] = f"{west},{south},{east},{north}"
        matches.append(entry)
    return matches


def _photon_name(properties: dict[str, Any]) -> str:
    values = [properties.get(key) for key in ("name", "city", "state", "country")]
    return ", ".join(dict.fromkeys(str(value) for value in values if value))


def _attribution(provider: str) -> str:
    suffix = "; geocoding by Photon" if provider == GEOCODER_PHOTON else ""
    return "© OpenStreetMap contributors" + suffix


def _number(raw: Any) -> float | None:
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return None
