import os
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, safe_feature_count
from qgis_ai_agent.qgis_tools.project.tree import (
    describe_groups,
    ensure_group,
    layer_names,
    project,
    require_group,
)

VECTOR_SUFFIXES = (".shp", ".geojson", ".json", ".gpkg", ".kml", ".gml", ".csv", ".tab", ".gpx")
RASTER_SUFFIXES = (".tif", ".tiff", ".geotiff", ".png", ".jpg", ".jpeg", ".img", ".asc", ".vrt")
VECTOR = "vector"
RASTER = "raster"
OGR = "ogr"


class AddLayerTool(BaseTool):
    name = "add_layer"
    description = (
        "Добавить слой в проект из файла на диске или из источника данных. "
        "Тип определяется по расширению, если не указан явно."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "Файл должен существовать и открываться QGIS",
        "Группа, если указана, должна существовать или будет создана",
    ]
    examples = ["Загрузи /data/roads.geojson", "Добавь растр подложки в группу «Фон»"]
    params_schema = [
        {
            "name": "source",
            "type": "string",
            "description": "Путь к файлу или строка источника данных",
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Имя слоя в проекте. По умолчанию — имя файла без расширения.",
            "required": False,
        },
        {
            "name": "kind",
            "type": "string",
            "enum": [VECTOR, RASTER],
            "description": "Тип слоя. Без него определяется по расширению файла.",
            "required": False,
        },
        {
            "name": "group",
            "type": "string",
            "description": "Группа в дереве слоёв. Отсутствующая группа будет создана.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        source = (params.get("source") or "").strip()
        if not source:
            raise ValueError("Не указан источник слоя.")
        prepared = dict(params)
        prepared["source"] = source
        prepared["name"] = _wanted_name(params, source)
        prepared["kind"] = _wanted_kind(params, source)
        if _looks_like_path(source) and not os.path.exists(source):
            raise ValueError(f"Файла «{source}» нет на диске. Проверьте путь.")
        if prepared["name"] in layer_names():
            raise ValueError(
                f"Слой с именем «{prepared['name']}» уже есть в проекте. "
                "Задайте другое имя через name."
            )
        if params.get("group"):
            require_group_or_new(params["group"])
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        source = (params.get("source") or "").strip()
        name = _wanted_name(params, source)
        group = (params.get("group") or "").strip()
        tail = f" в группу «{group}»" if group else ""
        return f"Добавляю слой «{name}»{tail}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        source = (params.get("source") or "").strip()
        name = _wanted_name(params, source)
        kind = _wanted_kind(params, source)
        layer = _build(source, name, kind)
        if not layer.isValid():
            raise ValueError(f"QGIS не смог открыть «{source}»: {_reason(layer)}")
        group = (params.get("group") or "").strip()
        project().addMapLayer(layer, not group)
        if group:
            ensure_group(group).addLayer(layer)
        return _described(layer, kind, group)


def require_group_or_new(name: str) -> None:
    wanted = (name or "").strip()
    if not wanted:
        return
    if len(wanted) > 120:
        raise ValueError(f"Имя группы слишком длинное. {describe_groups()}")


def _build(source: str, name: str, kind: str) -> Any:
    if kind == RASTER:
        return QgsRasterLayer(source, name)
    return QgsVectorLayer(source, name, OGR)


def _described(layer: Any, kind: str, group: str) -> dict[str, Any]:
    described: dict[str, Any] = {"name": layer.name(), "kind": kind, "crs": crs_authid(layer)}
    if group:
        described["group"] = group
    if kind == VECTOR:
        described["geometry"] = geometry_type_name(layer)
        described["feature_count"] = safe_feature_count(layer)
    return described


def _wanted_name(params: dict[str, Any], source: str) -> str:
    given = (params.get("name") or "").strip()
    if given:
        return given
    base = os.path.basename(source.split("|")[0].split("?")[0])
    return os.path.splitext(base)[0] or "Новый слой"


def _wanted_kind(params: dict[str, Any], source: str) -> str:
    given = (params.get("kind") or "").strip().lower()
    if given in (VECTOR, RASTER):
        return given
    if given:
        raise ValueError(f"Неизвестный тип слоя «{given}». Доступны: {VECTOR}, {RASTER}.")
    suffix = os.path.splitext(source.split("|")[0].split("?")[0])[1].lower()
    return RASTER if suffix in RASTER_SUFFIXES else VECTOR


def _looks_like_path(source: str) -> bool:
    return "=" not in source.split("|")[0] and "://" not in source


def _reason(layer: Any) -> str:
    try:
        message = layer.error().summary()
    except Exception:
        message = ""
    return message or "источник не распознан или файл повреждён"
