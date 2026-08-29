from typing import Any

from qgis.core import QgsSettings

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
SETTINGS_KEY = "qgis_ai_agent/overpass_url"
QUERY_TIMEOUT_SEC = 90
ELEMENTS = ("node", "way", "relation")
AREA_NAME_KEYS = ("name", "name:en", "int_name")
RECURSE_DOWN = "(._;>;);"
GEOMETRY_ELEMENTS = {
    "points": ("node",),
    "lines": ("way",),
    "polygons": ("way", "relation"),
    "all": ELEMENTS,
}


def endpoint() -> str:
    try:
        stored = QgsSettings().value(SETTINGS_KEY, DEFAULT_ENDPOINT, type=str)
    except Exception:
        stored = ""
    return (stored or DEFAULT_ENDPOINT).strip()


def build_query(
    key: str = "",
    value: str = "",
    area: str = "",
    bbox: tuple[float, float, float, float] | None = None,
    geometry: str = "all",
    selectors: list[str] | None = None,
) -> str:
    statements = selectors or _from_tag(key, value, geometry)
    if area:
        return _wrapped(statements, _area_header(area), "(area.searchArea)")
    if bbox is None:
        raise ValueError("No search territory was given: either area or bbox is required.")
    return _wrapped(statements, _bbox_header(bbox), "")


def _from_tag(key: str, value: str, geometry: str) -> list[str]:
    selector = _selector(key, value)
    return [f"{element}{selector}" for element in GEOMETRY_ELEMENTS.get(geometry, ELEMENTS)]


def _wrapped(statements: list[str], header: str, binding: str) -> str:
    body = "\n".join(f"  {statement}{binding};" for statement in statements)
    return f"{header}(\n{body}\n);\n{RECURSE_DOWN}\nout body;"


def _area_header(area: str) -> str:
    clean = _escaped(area)
    matches = "\n".join(f'  area["{key}"="{clean}"];' for key in AREA_NAME_KEYS)
    return f"[out:xml][timeout:{QUERY_TIMEOUT_SEC}];\n(\n{matches}\n)->.searchArea;\n"


def _bbox_header(bbox: tuple[float, float, float, float]) -> str:
    west, south, east, north = bbox
    return f"[out:xml][timeout:{QUERY_TIMEOUT_SEC}][bbox:{south:.6f},{west:.6f},{north:.6f},{east:.6f}];\n"


def _selector(key: str, value: str) -> str:
    clean_key = _escaped(key)
    if not clean_key:
        raise ValueError("No OSM key was given, for example amenity or highway.")
    if not value:
        return f'["{clean_key}"]'
    return f'["{clean_key}"="{_escaped(value)}"]'


def _escaped(text: Any) -> str:
    return str(text or "").strip().replace("\\", "").replace('"', "")
