from typing import Any

from ai_agent.config.geocoder import (
    GEOCODER_NOMINATIM,
    GEOCODER_PHOTON,
    get_provider,
    get_url,
    validated_service_url,
)
from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_WEB_CONTENT, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.geocoding import parse_matches, search_url
from ai_agent.qgis_tools.web.http import checked_url, get_text, safe_url_label
from ai_agent.qgis_tools.web.url_policy import bounded_text, short_text

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
        checked_url(search_url(service_url, place, provider), resolve=False)
        return {"place": place, "_geocoder_provider": provider, "_geocoder_url": service_url}

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        matches = payload.get("matches") or []
        if not matches:
            return tr("Nothing found")
        first = str(matches[0].get("name") or "")
        return first if len(matches) == 1 else f"{first} +{len(matches) - 1}"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        place = bounded_text(params.get("place"), "place name", MAX_PLACE_CHARS)
        provider, service_url = _configuration(params, resolve=True)
        endpoint = search_url(service_url, place, provider)
        matches = parse_matches(get_text(endpoint), provider)
        if not matches:
            raise ValueError(NOTHING)
        return {
            "place": place,
            "service": safe_url_label(service_url),
            "matches": matches,
            "attribution": _attribution(provider),
        }


def _configuration(params: dict[str, Any], *, resolve: bool) -> tuple[str, str]:
    provider = str(params.get("_geocoder_provider") or get_provider())
    raw_url = params.get("_geocoder_url") or get_url()
    if provider not in {GEOCODER_PHOTON, GEOCODER_NOMINATIM}:
        raise ValueError("Choose Photon or Custom Nominatim in AI Agent Settings first.")
    if not raw_url:
        raise ValueError("Enter a custom Nominatim URL in AI Agent Settings first.")
    service_url = validated_service_url(raw_url)
    return provider, checked_url(service_url, resolve=resolve)


def _attribution(provider: str) -> str:
    suffix = "; geocoding by Photon" if provider == GEOCODER_PHOTON else ""
    return "© OpenStreetMap contributors" + suffix
