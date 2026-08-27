from typing import Any

from qgis_ai_agent.qgis_tools.osm.extent import canvas_bbox, parse_bbox
from qgis_ai_agent.qgis_tools.osm.load import SUBLAYERS
from qgis_ai_agent.qgis_tools.osm.selectors import SHAPE_HINT, normalize

CANVAS = "canvas"
DEFAULT_GEOMETRY = "all"
DEFAULT_SELECTOR_NAME = "OSM selection"


def selectors(params: dict[str, Any]) -> list[str]:
    raw = params.get("selectors")
    if not raw:
        return []
    if params.get("key"):
        raise ValueError("Give one of the two: key with value, or selectors — not both at once.")
    return normalize(raw)


def required_key(params: dict[str, Any]) -> str:
    key = (params.get("key") or "").strip()
    if not key:
        raise ValueError(
            "Neither key nor selectors was given. The simple case is a key such as amenity "
            f"or highway. Anything harder goes through selectors. {SHAPE_HINT}"
        )
    return key


def geometry(params: dict[str, Any]) -> str:
    wanted = (params.get("geometry") or DEFAULT_GEOMETRY).strip().lower()
    if wanted not in SUBLAYERS:
        raise ValueError(
            f"Unknown geometry '{params.get('geometry')}'. "
            f"Available: {', '.join(sorted(SUBLAYERS))}."
        )
    return wanted


def territory(params: dict[str, Any]) -> tuple[str, tuple[float, float, float, float] | None]:
    area = (params.get("area") or "").strip()
    raw_bbox = (params.get("bbox") or "").strip()
    if area and raw_bbox:
        raise ValueError("Give one of the two: area or bbox — not both at once.")
    if area:
        return area, None
    if raw_bbox.lower() == CANVAS:
        return "", canvas_bbox()
    if raw_bbox:
        return "", parse_bbox(raw_bbox)
    raise ValueError(
        "No territory was given. Pass area with a place name, or bbox — "
        f'a rectangle in degrees, or "{CANVAS}" for the current map view.'
    )


def wanted_name(params: dict[str, Any]) -> str:
    given = (params.get("name") or "").strip()
    if given:
        return given
    if params.get("selectors"):
        return DEFAULT_SELECTOR_NAME
    key = (params.get("key") or "osm").strip()
    value = (params.get("value") or "").strip()
    return f"{key}={value}" if value else key


def as_text(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{number:.6f}" for number in bbox)
