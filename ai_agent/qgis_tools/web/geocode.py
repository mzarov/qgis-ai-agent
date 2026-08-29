import json
from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from ai_agent.qgis_tools.web.http import encoded, get_text

NOMINATIM = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit={limit}&q={query}"
MAX_MATCHES = 5
NOTHING = "Nominatim knows no such place — check the spelling or add the region."


class GeocodeTool(BaseTool):
    name = "geocode"
    description = (
        "Find a place by name through OSM Nominatim: coordinates, bounding box "
        "and the place type. The bounding box slots straight into download_osm "
        "as bbox, and the coordinates into zooming or annotations."
    )
    skill = "web"
    safety = SAFETY_READ
    constraints = ["A public service with a strict rate limit — one lookup per place"]
    examples = ["Where is Divnomorskoye?", "Coordinates of the Kazan Kremlin"]
    params_schema = [
        {"name": "place", "type": "string", "description": "Place name, any language", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Looking up '{0}' on the map.").format(str(params.get("place") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        place = str(params.get("place") or "").strip()
        if not place:
            raise ValueError("The place name is empty.")
        body = get_text(NOMINATIM.format(limit=MAX_MATCHES, query=encoded(place)))
        matches = parse_matches(body)
        if not matches:
            raise ValueError(NOTHING)
        return {"place": place, "matches": matches, "attribution": "© OpenStreetMap contributors"}


def parse_matches(body: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(body or "[]")
    except ValueError:
        return []
    matches = []
    for item in raw if isinstance(raw, list) else []:
        box = item.get("boundingbox") or []
        entry = {
            "name": item.get("display_name", ""),
            "type": f"{item.get('category', '')}/{item.get('type', '')}",
            "lat": _number(item.get("lat")),
            "lon": _number(item.get("lon")),
        }
        if len(box) == 4:
            south, north, west, east = (_number(edge) for edge in box)
            entry["bbox"] = f"{west},{south},{east},{north}"
        matches.append(entry)
    return matches


def _number(raw: Any) -> float:
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return 0.0
