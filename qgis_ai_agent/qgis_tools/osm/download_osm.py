from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.osm.args import (
    CANVAS,
    as_text,
    geometry,
    required_key,
    selectors,
    territory,
    wanted_name,
)
from qgis_ai_agent.qgis_tools.osm.fetch import fetch
from qgis_ai_agent.qgis_tools.osm.load import SUBLAYERS, load_sublayers, write_payload
from qgis_ai_agent.qgis_tools.osm.overpass import build_query

NOTHING_FOUND = (
    "Overpass отработал, но объектов по такому запросу нет. Проверьте ключ и "
    "значение — например, amenity=cafe, а не amenity=кафе, — либо расширьте территорию."
)


class DownloadOsmTool(BaseTool):
    name = "download_osm"
    description = (
        "Скачать данные OpenStreetMap через Overpass и добавить их слоями в проект. "
        "Простой случай — пара ключ-значение вроде amenity=cafe. Сложный — список "
        "селекторов Overpass: несколько тегов разом, регулярные выражения, "
        "исключения. Территория задаётся именем места или прямоугольником."
    )
    skill = "osm"
    safety = SAFETY_WRITE
    constraints = [
        "Нужен либо area, либо bbox — без территории запрос не выполняется",
        "Ключи и значения OSM пишутся по-английски: amenity=cafe, highway=primary",
        "key с value или selectors — что-то одно",
    ]
    examples = [
        "Скачай кафе в Москве",
        "Загрузи дороги в текущем виде карты",
        "Скачай кафе, рестораны и бары одним слоем",
        "Все дороги кроме грунтовых",
    ]
    params_schema = [
        {
            "name": "key",
            "type": "string",
            "description": (
                "Ключ OSM для простого случая: amenity, highway, building, landuse. "
                "Для чего-то сложнее используйте selectors."
            ),
            "required": False,
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
            "name": "selectors",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Селекторы Overpass, по одному на строку списка, например "
                '["node[\'amenity\'~\'cafe|restaurant\']", "way[\'shop\']"]. '
                "Так выражается всё, чего не покрывает пара ключ-значение: "
                "несколько тегов, регулярные выражения, исключения через != и !~. "
                "Территорию, таймаут и вывод дописывает плагин — их указывать не надо."
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
        chosen = selectors(params)
        prepared = dict(params)
        prepared["key"] = "" if chosen else required_key(params)
        prepared["selectors"] = chosen
        prepared["geometry"] = geometry(params)
        prepared["name"] = wanted_name(params)
        area, bbox = territory(params)
        prepared["area"] = area
        prepared["bbox"] = as_text(bbox) if bbox else ""
        build_query(
            prepared["key"], params.get("value") or "", area, bbox, prepared["geometry"], chosen
        )
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = wanted_name(params)
        where = (params.get("area") or "").strip() or "заданном охвате"
        return f"Скачиваю из OSM «{name}» в {where}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        chosen = selectors(params)
        key = "" if chosen else required_key(params)
        wanted = geometry(params)
        name = wanted_name(params)
        area, bbox = territory(params)
        query = build_query(key, params.get("value") or "", area, bbox, wanted, chosen)
        path = write_payload(fetch(query), name)
        loaded = load_sublayers(path, wanted, name)
        if not loaded:
            raise ValueError(NOTHING_FOUND)
        return {
            "layers": loaded,
            "total_features": sum(item["feature_count"] for item in loaded),
            "source": path,
        }
