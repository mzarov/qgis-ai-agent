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

from ai_agent.qgis_tools.osm.tags import promote_tags

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
FOLDER_PREFIX = "ai-agent-osm-"
PROJECT_FOLDER = "osm"
LOG_TAG = "AI Agent"
SUFFIX = ".osm"
GPKG_SUFFIX = ".gpkg"
OGR = "ogr"
MAX_STEM_ATTEMPTS = 1000
TEMP_NOTE = (
    "The project is not saved, so the downloaded data lives in a temporary folder that the "
    "system may clear. Save the project, or export the layers with export_layer, to keep them."
)


def write_payload(text: str, stem: str) -> tuple[str, bool]:
    """Write the Overpass answer; return its path and whether it sits in a temporary folder.

    A saved project keeps its downloads in `<project home>/osm/`, so the layers
    still open after a reboot; an unsaved one has no home and falls back to temp.
    """
    home = _project_home()
    if home:
        folder = os.path.join(home, PROJECT_FOLDER)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, _unique_stem(folder, _slug(stem)) + SUFFIX)
        _write(path, text)
        return path, False
    folder = tempfile.mkdtemp(prefix=FOLDER_PREFIX)
    os.chmod(folder, 0o700)
    path = os.path.join(folder, f"{_slug(stem)}{SUFFIX}")
    _write(path, text)
    os.chmod(path, 0o600)
    return path, True


def storage_note(temporary: bool) -> dict[str, str]:
    return {"storage_note": TEMP_NOTE} if temporary else {}


def load_sublayers(path: str, geometry: str, name: str) -> list[dict[str, Any]]:
    """Add each non-empty sublayer; drop the raw .osm once no layer reads it."""
    loaded: list[dict[str, Any]] = []
    raw_in_use = False
    for sublayer in SUBLAYERS.get(geometry, SUBLAYERS["all"]):
        described = _load_one(path, sublayer, name, geometry)
        if described is not None:
            raw_in_use = raw_in_use or described["source"] == path
            loaded.append(described)
    if not raw_in_use:
        _remove(path)
    return loaded


def _load_one(path: str, sublayer: str, name: str, geometry: str) -> dict[str, Any] | None:
    raw = QgsVectorLayer(f"{path}|layername={sublayer}", _title(name, sublayer, geometry), OGR)
    if not raw.isValid():
        return None
    count = _count(raw)
    if not count:
        return None
    materialized = _materialized(raw, path, sublayer)
    layer = materialized or raw
    promoted = promote_tags(layer)
    QgsProject.instance().addMapLayer(layer)
    described = {
        "name": layer.name(),
        "kind": READABLE.get(sublayer, sublayer),
        "feature_count": count,
        "source": _gpkg_path(path, sublayer) if materialized is not None else path,
    }
    if promoted:
        described["tag_fields"] = promoted
    return described


def _gpkg_path(path: str, sublayer: str) -> str:
    return f"{path[: -len(SUFFIX)]}_{sublayer}{GPKG_SUFFIX}"


def _materialized(raw: Any, path: str, sublayer: str) -> Any:
    target = _gpkg_path(path, sublayer)
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
            f"OSM layer stays read-only, GeoPackage conversion failed: {err}", LOG_TAG, Qgis.MessageLevel.Warning
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


def _project_home() -> str:
    try:
        home = QgsProject.instance().homePath()
    except Exception:
        return ""
    return home if isinstance(home, str) and home.strip() and os.path.isdir(home) else ""


def _unique_stem(folder: str, stem: str) -> str:
    """A stem whose .osm and every .gpkg copy are all free in the folder."""
    for attempt in range(1, MAX_STEM_ATTEMPTS + 1):
        candidate = stem if attempt == 1 else f"{stem}_{attempt}"
        taken = [os.path.join(folder, candidate + SUFFIX)]
        taken += [_gpkg_path(taken[0], sublayer) for sublayer in SUBLAYERS["all"]]
        if not any(os.path.exists(item) for item in taken):
            return candidate
    raise ValueError(f"The folder {folder} already holds too many downloads named '{stem}'. Pick another name.")


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError as err:
        QgsMessageLog.logMessage(f"Could not remove the raw OSM file {path}: {err}", LOG_TAG, Qgis.MessageLevel.Warning)


def _slug(text: str) -> str:
    kept = [char if char.isalnum() or char in "-_" else "_" for char in str(text or "osm")]
    return "".join(kept)[:60] or "osm"
