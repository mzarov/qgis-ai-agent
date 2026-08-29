import os
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, safe_feature_count
from ai_agent.qgis_tools.project.tree import (
    describe_groups,
    ensure_group,
    layer_names,
    project,
)

VECTOR_SUFFIXES = (".shp", ".geojson", ".json", ".gpkg", ".kml", ".gml", ".csv", ".tab", ".gpx")
RASTER_SUFFIXES = (".tif", ".tiff", ".geotiff", ".png", ".jpg", ".jpeg", ".img", ".asc", ".vrt")
VECTOR = "vector"
RASTER = "raster"
OGR = "ogr"
MAX_GROUP_NAME = 120


class AddLayerTool(BaseTool):
    name = "add_layer"
    description = (
        "Add a layer to the project from a file on disk or from a data source. "
        "The kind is guessed from the extension unless it is given explicitly."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "The file must exist and be readable by QGIS",
        "A group, if given, must exist or it will be created",
    ]
    examples = ["Load /data/roads.geojson", "Add the basemap raster to the 'Background' group"]
    params_schema = [
        {
            "name": "source",
            "type": "string",
            "description": "Path to the file or a data source string",
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name in the project. Defaults to the file name without extension.",
            "required": False,
        },
        {
            "name": "kind",
            "type": "string",
            "enum": [VECTOR, RASTER],
            "description": "Layer kind. Without it the file extension decides.",
            "required": False,
        },
        {
            "name": "group",
            "type": "string",
            "description": "Group in the layer tree. A group that does not exist will be created.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        source = (params.get("source") or "").strip()
        if not source:
            raise ValueError("No layer source was given.")
        prepared = dict(params)
        prepared["source"] = source
        prepared["name"] = _wanted_name(params, source)
        prepared["kind"] = _wanted_kind(params, source)
        if _looks_like_path(source) and not os.path.exists(source):
            raise ValueError(f"There is no file '{source}' on disk. Check the path.")
        if prepared["name"] in layer_names():
            raise ValueError(
                f"A layer named '{prepared['name']}' is already in the project. "
                "Give another name through the name parameter."
            )
        check_group_name(params.get("group"))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        source = (params.get("source") or "").strip()
        name = _wanted_name(params, source)
        group = (params.get("group") or "").strip()
        tail = tr(" into group '{0}'").format(group) if group else ""
        return tr("Adding layer '{0}'{1}.").format(name, tail)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        source = (params.get("source") or "").strip()
        name = _wanted_name(params, source)
        kind = _wanted_kind(params, source)
        layer = _build(source, name, kind)
        if not layer.isValid():
            raise ValueError(f"QGIS could not open '{source}': {_reason(layer)}")
        group = (params.get("group") or "").strip()
        project().addMapLayer(layer, not group)
        if group:
            ensure_group(group).addLayer(layer)
        return _described(layer, kind, group)


def check_group_name(name: Any) -> None:
    wanted = str(name or "").strip()
    if len(wanted) > MAX_GROUP_NAME:
        raise ValueError(f"The group name is too long. {describe_groups()}")


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
    return os.path.splitext(base)[0] or "New layer"


def _wanted_kind(params: dict[str, Any], source: str) -> str:
    given = (params.get("kind") or "").strip().lower()
    if given in (VECTOR, RASTER):
        return given
    if given:
        raise ValueError(f"Unknown layer kind '{given}'. Available: {VECTOR}, {RASTER}.")
    suffix = os.path.splitext(source.split("|")[0].split("?")[0])[1].lower()
    return RASTER if suffix in RASTER_SUFFIXES else VECTOR


def _looks_like_path(source: str) -> bool:
    return "=" not in source.split("|")[0] and "://" not in source


def _reason(layer: Any) -> str:
    try:
        message = layer.error().summary()
    except Exception:
        message = ""
    return message or "the source was not recognised or the file is damaged"
