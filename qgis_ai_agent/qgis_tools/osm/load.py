import os
import tempfile
from typing import Any

from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsMessageLog,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from qgis_ai_agent.qgis_tools.osm.tags import promote_tags

SUBLAYERS = {
    "points": ("points",),
    "lines": ("lines", "multilinestrings"),
    "polygons": ("multipolygons",),
    "all": ("points", "lines", "multilinestrings", "multipolygons"),
}
READABLE = {
    "points": "points",
    "lines": "lines",
    "multilinestrings": "lines",
    "multipolygons": "polygons",
}
FOLDER_PREFIX = "qgis-ai-agent-osm-"
LOG_TAG = "QGIS AI Agent"
SUFFIX = ".osm"
OGR = "ogr"


def write_payload(text: str, stem: str) -> str:
    folder = tempfile.mkdtemp(prefix=FOLDER_PREFIX)
    os.chmod(folder, 0o700)
    path = os.path.join(folder, f"{_slug(stem)}{SUFFIX}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)
    return path


def load_sublayers(path: str, geometry: str, name: str) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for sublayer in SUBLAYERS.get(geometry, SUBLAYERS["all"]):
        described = _load_one(path, sublayer, name, geometry)
        if described is not None:
            loaded.append(described)
    return loaded


def _load_one(path: str, sublayer: str, name: str, geometry: str) -> dict[str, Any] | None:
    raw = QgsVectorLayer(f"{path}|layername={sublayer}", _title(name, sublayer, geometry), OGR)
    if not raw.isValid():
        return None
    count = _count(raw)
    if not count:
        return None
    layer = _materialized(raw, path, sublayer) or raw
    promoted = promote_tags(layer)
    QgsProject.instance().addMapLayer(layer)
    described = {"name": layer.name(), "kind": READABLE.get(sublayer, sublayer), "feature_count": count}
    if promoted:
        described["tag_fields"] = promoted
    return described


def _materialized(raw: Any, path: str, sublayer: str) -> Any:
    target = f"{path[: -len(SUFFIX)]}_{sublayer}.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
    try:
        error = QgsVectorFileWriter.writeAsVectorFormatV3(raw, target, QgsCoordinateTransformContext(), options)
        code = error[0] if isinstance(error, tuple) else error
        if code != QgsVectorFileWriter.WriterError.NoError:
            raise ValueError(str(error))
        layer = QgsVectorLayer(target, raw.name(), OGR)
        if not layer.isValid() or not _count(layer):
            raise ValueError("the GeoPackage copy came back empty")
    except Exception as err:
        QgsMessageLog.logMessage(
            f"OSM layer stays read-only, GeoPackage conversion failed: {err}", LOG_TAG, Qgis.Warning
        )
        return None
    return layer


def _title(name: str, sublayer: str, geometry: str) -> str:
    if geometry != "all" and len(SUBLAYERS.get(geometry, ())) == 1:
        return name
    return f"{name} — {READABLE.get(sublayer, sublayer)}"


def _count(layer: Any) -> int:
    try:
        known = int(layer.featureCount())
    except Exception:
        return 0
    return known if known >= 0 else _counted_by_hand(layer)


def _counted_by_hand(layer: Any) -> int:
    try:
        return sum(1 for _ in layer.getFeatures())
    except Exception:
        return 0


def _slug(text: str) -> str:
    kept = [char if char.isalnum() or char in "-_" else "_" for char in str(text or "osm")]
    return "".join(kept)[:60] or "osm"
