from typing import Any

from qgis.core import QgsSettings

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
SETTINGS_KEY = "qgis_ai_agent/overpass_url"
QUERY_TIMEOUT_SEC = 90
ELEMENTS = ("node", "way", "relation")
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
    key: str,
    value: str = "",
    area: str = "",
    bbox: tuple[float, float, float, float] | None = None,
    geometry: str = "all",
) -> str:
    selector = _selector(key, value)
    elements = GEOMETRY_ELEMENTS.get(geometry, ELEMENTS)
    if area:
        return _area_query(selector, elements, area)
    if bbox is None:
        raise ValueError("Не задана территория поиска: нужен либо area, либо bbox.")
    return _bbox_query(selector, elements, bbox)


def _area_query(selector: str, elements: tuple[str, ...], area: str) -> str:
    body = "\n".join(f'  {element}{selector}(area.searchArea);' for element in elements)
    return (
        f"[out:xml][timeout:{QUERY_TIMEOUT_SEC}];\n"
        f'area["name"="{_escaped(area)}"]->.searchArea;\n'
        f"(\n{body}\n);\n"
        "out body;\n>;\nout skel qt;"
    )


def _bbox_query(
    selector: str, elements: tuple[str, ...], bbox: tuple[float, float, float, float]
) -> str:
    west, south, east, north = bbox
    body = "\n".join(f"  {element}{selector};" for element in elements)
    return (
        f"[out:xml][timeout:{QUERY_TIMEOUT_SEC}]"
        f"[bbox:{south:.6f},{west:.6f},{north:.6f},{east:.6f}];\n"
        f"(\n{body}\n);\n"
        "out body;\n>;\nout skel qt;"
    )


def _selector(key: str, value: str) -> str:
    clean_key = _escaped(key)
    if not clean_key:
        raise ValueError("Не задан ключ OSM, например amenity или highway.")
    if not value:
        return f'["{clean_key}"]'
    return f'["{clean_key}"="{_escaped(value)}"]'


def _escaped(text: Any) -> str:
    return str(text or "").strip().replace("\\", "").replace('"', "")
