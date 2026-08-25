from typing import Any

from qgis.core import QgsCoordinateReferenceSystem

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.bag import properties_of, shown
from qgis_ai_agent.qgis_tools.project.catalogues import PROJECT_PROPERTIES
from qgis_ai_agent.qgis_tools.project.tree import project


class ConfigureProjectTool(BaseTool):
    name = "configure_project"
    description = (
        "Изменить настройки проекта: название и систему координат карты. "
        "Слои и их данные не трогает."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["CRS указывается идентификатором вида EPSG:3857"]
    examples = ["Переведи проект в веб-меркатор", "Назови проект «Транспорт города»"]
    params_schema = [
        {
            "name": "properties",
            "type": "object",
            "description": (
                'Что изменить: {"crs": "EPSG:3857", "title": "Транспорт города"}. '
                "Указывайте только то, что меняется."
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        properties = PROJECT_PROPERTIES.coerce_all(
            properties_of(params, PROJECT_PROPERTIES.subject)
        )
        if not properties:
            raise ValueError(
                "Не указано ни одного свойства. Доступны: "
                + ", ".join(PROJECT_PROPERTIES.names())
                + "."
            )
        if "crs" in properties:
            _require_crs(properties["crs"])
        prepared = dict(params)
        prepared["properties"] = properties
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        try:
            properties = properties_of(params, PROJECT_PROPERTIES.subject)
        except ValueError:
            return "Меняю настройки проекта."
        return f"Меняю настройки проекта: {shown(properties, PROJECT_PROPERTIES)}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        properties = PROJECT_PROPERTIES.coerce_all(
            properties_of(params, PROJECT_PROPERTIES.subject)
        )
        instance = project()
        if "title" in properties:
            instance.setTitle(properties["title"])
        if "crs" in properties:
            instance.setCrs(_require_crs(properties["crs"]))
        return {"applied": sorted(properties), "crs": _current_crs(instance)}


def _require_crs(value: Any) -> QgsCoordinateReferenceSystem:
    text = str(value or "").strip()
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        raise ValueError(
            f"«{text}» не распознано как система координат. Используйте "
            "идентификатор вида EPSG:4326 или EPSG:3857."
        )
    return crs


def _current_crs(instance: Any) -> str:
    try:
        return instance.crs().authid() or ""
    except Exception:
        return ""
