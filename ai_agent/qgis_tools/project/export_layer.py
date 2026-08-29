import os
from typing import Any

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import find_layer_by_name

FORMATS = {
    ".gpkg": "GPKG",
    ".geojson": "GeoJSON",
    ".shp": "ESRI Shapefile",
    ".csv": "CSV",
}


class ExportLayerTool(BaseTool):
    name = "export_layer"
    description = (
        "Save a vector layer to a file on disk — GeoPackage, GeoJSON, Shapefile "
        "or CSV, chosen by the path extension. Optionally only the selected "
        "features, and optionally reprojected."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "The layer must exist and be a vector layer",
        "The target folder must exist; the extension decides the format",
    ]
    examples = ["Save the roads layer to /data/roads.gpkg", "Export what I selected to GeoJSON"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "path",
            "type": "string",
            "description": f"Target file path; the extension picks the format ({', '.join(sorted(FORMATS))})",
            "required": True,
        },
        {
            "name": "selected_only",
            "type": "boolean",
            "description": "Export only the features selected on the map",
            "required": False,
        },
        {
            "name": "crs",
            "type": "string",
            "description": "Reproject on the way out, e.g. EPSG:4326. Defaults to the layer CRS.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "")
        path = _checked_path(params.get("path") or "")
        if params.get("selected_only") and not int(layer.selectedFeatureCount() or 0):
            raise ValueError(
                f"Nothing is selected on '{layer.name()}', so a selected-only export would be empty. "
                "Select features first, or drop selected_only."
            )
        _checked_crs(params.get("crs"))
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["path"] = path
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        path = (params.get("path") or "").strip()
        return tr("Exporting layer '{0}' to {1}.").format(layer_name, path)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _require_vector(params.get("layer_name") or "")
        path = _checked_path(params.get("path") or "")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = FORMATS[_suffix(path)]
        options.onlySelectedFeatures = bool(params.get("selected_only"))
        crs = _checked_crs(params.get("crs"))
        if crs is not None:
            options.ct = _transform(layer, crs)
        error = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsCoordinateTransformContext(), options)
        code = error[0] if isinstance(error, tuple) else error
        if code != QgsVectorFileWriter.WriterError.NoError:
            reason = error[1] if isinstance(error, tuple) and len(error) > 1 else code
            raise ValueError(f"QGIS could not write '{path}': {reason}.")
        return {
            "layer": layer.name(),
            "path": path,
            "format": options.driverName,
            "selected_only": options.onlySelectedFeatures,
        }


def _require_vector(layer_name: str) -> Any:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer — rasters export through processing.")
    return layer


def _suffix(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _checked_path(raw: str) -> str:
    path = raw.strip()
    suffix = _suffix(path)
    if suffix not in FORMATS:
        raise ValueError(f"Unknown export format '{suffix or path}'. Available: {', '.join(sorted(FORMATS))}.")
    folder = os.path.dirname(path) or "."
    if not os.path.isdir(folder):
        raise ValueError(f"The folder '{folder}' does not exist — create it or pick another path.")
    return path


def _checked_crs(raw: Any) -> Any:
    text = str(raw or "").strip()
    if not text:
        return None
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        raise ValueError(f"'{text}' is not a coordinate system. Use an identifier such as EPSG:4326.")
    return crs


def _transform(layer: Any, crs: Any) -> Any:
    return QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
