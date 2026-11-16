from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ai_agent.config.geocoder import GEOCODER_DISABLED, get_provider, get_url, validated_service_url
from ai_agent.qgis_tools.common.geocoding import RELATION, Bbox, Place, find_places
from ai_agent.qgis_tools.osm.extent import checked_bbox

PROVIDER_KEY = "_geocoder_provider"
URL_KEY = "_geocoder_url"
# Overpass numbers the area made from a relation as the relation's id plus this.
RELATION_AREA_BASE = 3_600_000_000


@dataclass(frozen=True)
class Geocoder:
    provider: str
    url: str

    @property
    def host(self) -> str:
        try:
            return urlsplit(self.url).hostname or self.url
        except ValueError:
            return self.url


@dataclass(frozen=True)
class Territory:
    area: str = ""
    bbox: Bbox | None = None
    area_id: int = 0
    found: str = ""


def configured_geocoder() -> Geocoder | None:
    provider = get_provider()
    if provider == GEOCODER_DISABLED:
        return None
    try:
        return Geocoder(provider, validated_service_url(get_url()))
    except ValueError:
        return None


def pinned_geocoder(params: dict[str, Any]) -> Geocoder | None:
    provider, url = str(params.get(PROVIDER_KEY) or ""), str(params.get(URL_KEY) or "")
    return Geocoder(provider, url) if provider and url else None


def planned_geocoder(params: dict[str, Any]) -> Geocoder | None:
    # Only the service the plan line named, and only while Settings still name it.
    pinned = pinned_geocoder(params)
    return pinned if pinned is not None and pinned == configured_geocoder() else None


def locate(area: str, bbox: Bbox | None, geocoder: Geocoder | None, feedback: Any = None) -> Territory:
    named = Territory(area=area, bbox=bbox)
    if not area or geocoder is None:
        return named
    try:
        places = find_places(geocoder.url, area, geocoder.provider, feedback)
    except ValueError:
        return named
    return (_from_place(places[0]) if places else None) or named


def _from_place(place: Place) -> Territory | None:
    if place.osm_type == RELATION and place.osm_id:
        return Territory(area_id=RELATION_AREA_BASE + place.osm_id, found=place.name)
    if place.bbox is None:
        return None
    try:
        return Territory(bbox=checked_bbox(*place.bbox), found=place.name)
    except ValueError:
        return None
