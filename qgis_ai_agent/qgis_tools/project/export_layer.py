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

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import bind_layer_reference, find_layer_by_id, find_layer_by_name
from qgis_ai_agent.qgis_tools.common.paths import check_overwrites, outputs_safety, related_output_paths

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
    external_effect = True
    constraints = [
        "The layer must exist and be a vector layer",
        "The target folder must exist; the extension decides the format",
        "An existing target is never replaced unless overwrite=true",
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
            "name": "layer_id",
            "type": "string",
            "description": "Stable layer id returned by list_layers; use it to disambiguate duplicate names",
            "required": False,
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
        {
            "name": "overwrite",
            "type": "boolean",
            "description": "Replace an existing target file. Requires an additional destructive confirmation.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer_name = params.get("layer_name") or ""
        layer_id = str(params.get("layer_id") or "").strip()
        layer = _require_vector(layer_name, layer_id) if layer_id else _require_vector(layer_name)
        path = _checked_path(params.get("path") or "")
        outputs = related_output_paths(path)
        check_overwrites(outputs, bool(params.get("overwrite")))
        selected_ids = _selected_ids(layer) if params.get("selected_only") else []
        if params.get("selected_only") and not selected_ids:
            raise ValueError(_nothing_selected(layer))
        _checked_crs(params.get("crs"))
        prepared = bind_layer_reference(params, layer)
        prepared["path"] = path
        prepared["_output_paths"] = outputs
        if params.get("selected_only"):
            prepared["_selected_feature_ids"] = selected_ids
        return prepared

    def safety_for(self, params: dict[str, Any]) -> str:
        outputs = params.get("_output_paths") or related_output_paths(str(params.get("path") or ""))
        return outputs_safety(outputs, bool(params.get("overwrite")))

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        path = (params.get("path") or "").strip()
        if params.get("overwrite"):
            return tr("Overwriting {0} with exported layer '{1}'.").format(path, layer_name)
        return tr("Exporting layer '{0}' to {1}.").format(layer_name, path)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _prepared_vector(params)
        _validate_selection(layer, params)
        path = _checked_path(params.get("path") or "")
        check_overwrites(related_output_paths(path), bool(params.get("overwrite")))
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


def _require_vector(layer_name: str, layer_id: str = "") -> Any:
    identifier = str(layer_id or "").strip()
    layer = find_layer_by_id(identifier) if identifier else find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer — rasters export through processing.")
    return layer


def _prepared_vector(params: dict[str, Any]) -> Any:
    return _require_vector(params.get("layer_name") or "", params.get("layer_id") or "")


def _selected_ids(layer: Any) -> list[int]:
    try:
        return sorted(int(identifier) for identifier in layer.selectedFeatureIds())
    except Exception:
        return []


def _validate_selection(layer: Any, params: dict[str, Any]) -> None:
    if not params.get("selected_only"):
        return
    planned = params.get("_selected_feature_ids")
    if not isinstance(planned, list):
        if not _selected_ids(layer):
            raise ValueError(_nothing_selected(layer))
        return
    current = _selected_ids(layer)
    if current != [int(identifier) for identifier in planned]:
        raise ValueError(
            "The selected features changed after this export was planned. "
            "Nothing was written; review the selection and plan the export again."
        )


def _nothing_selected(layer: Any) -> str:
    return (
        f"Nothing is selected on '{layer.name()}', so a selected-only export would be empty. "
        "Select features first, or drop selected_only."
    )


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
