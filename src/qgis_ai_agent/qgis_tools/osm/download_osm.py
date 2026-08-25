from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.osm.extent import canvas_bbox, parse_bbox
from qgis_ai_agent.qgis_tools.osm.fetch import fetch
from qgis_ai_agent.qgis_tools.osm.load import SUBLAYERS, load_sublayers, write_payload
from qgis_ai_agent.qgis_tools.osm.overpass import build_query

CANVAS = "canvas"
DEFAULT_GEOMETRY = "all"
NOTHING_FOUND = (
    "Overpass отработал, но объектов по такому запросу нет. Проверьте ключ и "
    "значение — например, amenity=cafe, а не amenity=кафе, — либо расширьте территорию."
)


class DownloadOsmTool(BaseTool):
    name = "download_osm"
    description = (
        "Скачать данные OpenStreetMap через Overpass и добавить их слоями в проект: "
        "кафе, дороги, здания, водоёмы и прочее по паре ключ-значение OSM. "
        "Территория задаётся именем места или прямоугольником."
    )
    skill = "osm"
    safety = SAFETY_WRITE
    constraints = [
        "Нужен либо area, либо bbox — без территории запрос не выполняется",
        "Ключи и значения OSM пишутся по-английски: amenity=cafe, highway=primary",
    ]
    examples = [
        "Скачай кафе в Москве",
        "Загрузи дороги в текущем виде карты",
        "Добавь здания из OSM по этому охвату",
    ]
    params_schema = [
        {
            "name": "key",
            "type": "string",
            "description": "Ключ OSM: amenity, highway, building, landuse, natural, shop",
            "required": True,
        },
        {
            "name": "value",
            "type": "string",
            "description": (
                "Значение ключа: cafe, primary, residential. Без него берутся все "
                "объекты с таким ключом."
            ),
            "required": False,
        },
        {
            "name": "area",
            "type": "string",
            "description": (
                "Имя территории в OSM: Москва, Berlin, Тверская область. "
                "Взаимоисключимо с bbox."
            ),
            "required": False,
        },
        {
            "name": "bbox",
            "type": "string",
            "description": (
                'Прямоугольник "запад,юг,восток,север" в градусах EPSG:4326, '
                f'либо "{CANVAS}" — текущий вид карты.'
            ),
            "required": False,
        },
        {
            "name": "geometry",
            "type": "string",
            "enum": sorted(SUBLAYERS),
            "description": (
                "Какие геометрии загрузить: points — точки, lines — линии, "
                "polygons — полигоны, all — всё найденное."
            ),
            "required": False,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Имя слоя. По умолчанию собирается из ключа и значения.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(params)
        prepared["key"] = _required_key(params)
        prepared["geometry"] = _geometry(params)
        prepared["name"] = _wanted_name(params)
        area, bbox = _territory(params)
        prepared["area"] = area
        prepared["bbox"] = _as_text(bbox) if bbox else ""
        build_query(prepared["key"], params.get("value") or "", area, bbox, prepared["geometry"])
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = _wanted_name(params)
        where = (params.get("area") or "").strip() or "заданном охвате"
        return f"Скачиваю из OSM «{name}» в {where}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        key = _required_key(params)
        geometry = _geometry(params)
        name = _wanted_name(params)
        area, bbox = _territory(params)
        query = build_query(key, params.get("value") or "", area, bbox, geometry)
        path = write_payload(fetch(query), name)
        loaded = load_sublayers(path, geometry, name)
        if not loaded:
            raise ValueError(NOTHING_FOUND)
        return {
            "layers": loaded,
            "total_features": sum(item["feature_count"] for item in loaded),
            "source": path,
        }


def _required_key(params: dict[str, Any]) -> str:
    key = (params.get("key") or "").strip()
    if not key:
        raise ValueError("Не указан ключ OSM. Например: amenity, highway, building.")
    return key


def _geometry(params: dict[str, Any]) -> str:
    wanted = (params.get("geometry") or DEFAULT_GEOMETRY).strip().lower()
    if wanted not in SUBLAYERS:
        raise ValueError(
            f"Неизвестная геометрия «{params.get('geometry')}». "
            f"Доступны: {', '.join(sorted(SUBLAYERS))}."
        )
    return wanted


def _territory(params: dict[str, Any]) -> tuple[str, tuple[float, float, float, float] | None]:
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


def _wanted_name(params: dict[str, Any]) -> str:
    given = (params.get("name") or "").strip()
    if given:
        return given
    key = (params.get("key") or "osm").strip()
    value = (params.get("value") or "").strip()
    return f"{key}={value}" if value else key


def _as_text(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{number:.6f}" for number in bbox)
