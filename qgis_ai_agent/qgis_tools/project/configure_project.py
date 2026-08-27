from typing import Any

from qgis.core import QgsCoordinateReferenceSystem

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.properties import properties_of, shown
from qgis_ai_agent.qgis_tools.project.catalogues import PROJECT_PROPERTIES
from qgis_ai_agent.qgis_tools.project.tree import project


class ConfigureProjectTool(BaseTool):
    name = "configure_project"
    description = (
        "Change the project settings: title and map coordinate system. "
        "Leaves the layers and their data alone."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["The CRS is given as an identifier such as EPSG:3857"]
    examples = ["Switch the project to web mercator", "Name the project 'City transport'"]
    params_schema = [
        {
            "name": "properties",
            "type": "object",
            "description": (
                'What to change: {"crs": "EPSG:3857", "title": "City transport"}. '
                "Pass only what actually changes."
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
                "No property was given. Available: "
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
            return tr("Changing the project settings.")
        return tr("Changing the project settings: {0}.").format(shown(properties, PROJECT_PROPERTIES))

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
            f"'{text}' was not recognised as a coordinate system. Use "
            "an identifier such as EPSG:4326 or EPSG:3857."
        )
    return crs


def _current_crs(instance: Any) -> str:
    try:
        return instance.crs().authid() or ""
    except Exception:
        return ""
