from typing import Any

from qgis_ai_agent.qgis_tools.osm.extent import canvas_bbox, parse_bbox
from qgis_ai_agent.qgis_tools.osm.load import SUBLAYERS
from qgis_ai_agent.qgis_tools.osm.selectors import SHAPE_HINT, normalize

CANVAS = "canvas"
DEFAULT_GEOMETRY = "all"
DEFAULT_SELECTOR_NAME = "Выборка OSM"


def selectors(params: dict[str, Any]) -> list[str]:
    raw = params.get("selectors")
    if not raw:
        return []
    if params.get("key"):
        raise ValueError("Укажите что-то одно: key с value или selectors, а не оба сразу.")
    return normalize(raw)


def required_key(params: dict[str, Any]) -> str:
    key = (params.get("key") or "").strip()
    if not key:
        raise ValueError(
            "Не указан ни key, ни selectors. Простой случай — key вроде amenity "
            f"или highway. Сложнее — selectors. {SHAPE_HINT}"
        )
    return key


def geometry(params: dict[str, Any]) -> str:
    wanted = (params.get("geometry") or DEFAULT_GEOMETRY).strip().lower()
    if wanted not in SUBLAYERS:
        raise ValueError(
            f"Неизвестная геометрия «{params.get('geometry')}». "
            f"Доступны: {', '.join(sorted(SUBLAYERS))}."
        )
    return wanted


def territory(params: dict[str, Any]) -> tuple[str, tuple[float, float, float, float] | None]:
    area = (params.get("area") or "").strip()
    raw_bbox = (params.get("bbox") or "").strip()
    if area and raw_bbox:
        raise ValueError("Укажите что-то одно: area или bbox, а не оба сразу.")
    if area:
        return area, None
    if raw_bbox.lower() == CANVAS:
        return "", canvas_bbox()
    if raw_bbox:
        return "", parse_bbox(raw_bbox)
    raise ValueError(
        "Не задана территория. Укажите area с именем места или bbox — "
        f'прямоугольник в градусах либо "{CANVAS}" для текущего вида карты.'
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
