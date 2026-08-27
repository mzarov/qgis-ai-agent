import os
import tempfile
from typing import Any

from qgis.core import QgsProject, QgsVectorLayer

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
FOLDER = "qgis_ai_agent_osm"
SUFFIX = ".osm"
OGR = "ogr"


def write_payload(text: str, stem: str) -> str:
    folder = os.path.join(tempfile.gettempdir(), FOLDER)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{_slug(stem)}{SUFFIX}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def load_sublayers(path: str, geometry: str, name: str) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for sublayer in SUBLAYERS.get(geometry, SUBLAYERS["all"]):
        described = _load_one(path, sublayer, name, geometry)
        if described is not None:
            loaded.append(described)
    return loaded


def _load_one(path: str, sublayer: str, name: str, geometry: str) -> dict[str, Any] | None:
    layer = QgsVectorLayer(f"{path}|layername={sublayer}", _title(name, sublayer, geometry), OGR)
    if not layer.isValid():
        return None
    count = _count(layer)
    if not count:
        return None
    QgsProject.instance().addMapLayer(layer)
    return {"name": layer.name(), "kind": READABLE.get(sublayer, sublayer), "feature_count": count}


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
