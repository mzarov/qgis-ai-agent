import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.config.geocoder import GEOCODER_NOMINATIM, GEOCODER_PHOTON
from ai_agent.qgis_tools.common.http import USER_AGENT
from ai_agent.qgis_tools.common.network import send

MAX_MATCHES = 5
MAX_ANSWER_BYTES = 1024 * 1024
RELATION = "relation"
WAY = "way"
NODE = "node"
PHOTON_TYPES = {"R": RELATION, "W": WAY, "N": NODE}

Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Place:
    name: str
    kind: str
    lat: float
    lon: float
    bbox: Bbox | None = None
    osm_type: str = ""
    osm_id: int = 0

    def as_match(self) -> dict[str, Any]:
        match: dict[str, Any] = {"name": self.name, "type": self.kind, "lat": self.lat, "lon": self.lon}
        if self.bbox is not None:
            west, south, east, north = self.bbox
            match["bbox"] = f"{west},{south},{east},{north}"
        return match


def search_url(service_url: str, place: str, provider: str) -> str:
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


def find_places(service_url: str, place: str, provider: str, feedback: Any = None) -> list[Place]:
    # Safe off the main thread: nothing here reads the settings or the project.
    request = QNetworkRequest(QUrl(search_url(service_url, place, provider)))
    request.setRawHeader(b"User-Agent", USER_AGENT)
    answer = send(request, None, feedback)
    if answer.failed:
        raise ValueError(f"The geocoding service did not answer: {answer.error or 'no answer'}.")
    if len(answer.body) > MAX_ANSWER_BYTES:
        raise ValueError("The geocoding service sent an answer too large to read.")
    return parse_places(answer.body.decode("utf-8", errors="replace"), provider)


def parse_matches(body: str, provider: str = GEOCODER_NOMINATIM) -> list[dict[str, Any]]:
    return [place.as_match() for place in parse_places(body, provider)]


def parse_places(body: str, provider: str = GEOCODER_NOMINATIM) -> list[Place]:
    try:
        raw = json.loads(body or "[]")
    except ValueError:
        return []
    if provider == GEOCODER_PHOTON:
        return _photon_places(raw)
    return _nominatim_places(raw)


def _nominatim_places(raw: Any) -> list[Place]:
    places = []
    for item in raw[:MAX_MATCHES] if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        point = _point(item.get("lat"), item.get("lon"))
        if point is None:
            continue
        # Nominatim's box runs south, north, west, east.
        south, north, west, east = _four(item.get("boundingbox"))
        places.append(
            Place(
                name=item.get("display_name", ""),
                kind=f"{item.get('category', '')}/{item.get('type', '')}",
                lat=point[0],
                lon=point[1],
                bbox=_bbox(west, south, east, north),
                osm_type=str(item.get("osm_type") or "").lower(),
                osm_id=_identifier(item.get("osm_id")),
            )
        )
    return places


def _photon_places(raw: Any) -> list[Place]:
    features = raw.get("features", []) if isinstance(raw, dict) else []
    places = []
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
        point = _point(coordinates[1], coordinates[0])
        if point is None:
            continue
        # Photon's extent runs west, north, east, south.
        west, north, east, south = _four(properties.get("extent"))
        places.append(
            Place(
                name=_photon_name(properties),
                kind=f"{properties.get('osm_key', '')}/{properties.get('osm_value', '')}",
                lat=point[0],
                lon=point[1],
                bbox=_bbox(west, south, east, north),
                osm_type=PHOTON_TYPES.get(str(properties.get("osm_type") or "").upper(), ""),
                osm_id=_identifier(properties.get("osm_id")),
            )
        )
    return places


def _photon_name(properties: dict[str, Any]) -> str:
    values = [properties.get(key) for key in ("name", "city", "state", "country")]
    return ", ".join(dict.fromkeys(str(value) for value in values if value))


def _point(raw_lat: Any, raw_lon: Any) -> tuple[float, float] | None:
    lat, lon = _number(raw_lat), _number(raw_lon)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _four(raw: Any) -> tuple[float | None, float | None, float | None, float | None]:
    edges = raw if isinstance(raw, (list, tuple)) and len(raw) == 4 else (None, None, None, None)
    first, second, third, fourth = (_number(edge) for edge in edges)
    return first, second, third, fourth


def _bbox(west: float | None, south: float | None, east: float | None, north: float | None) -> Bbox | None:
    if west is None or south is None or east is None or north is None:
        return None
    return west, south, east, north


def _identifier(raw: Any) -> int:
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _number(raw: Any) -> float | None:
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return None
