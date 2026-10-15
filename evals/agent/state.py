"""What a task left in the project, as plain data a check can match: layers, project settings, files.

Only facts a request can change and a person would look at: a layer's geometry,
size, fields and their numeric sums, its renderer and the field it classifies by,
labels, opacity, visibility; the project CRS, layouts and annotations; the files
the run wrote into the task's folder. Point layers of a few features also list
their points in EPSG:4326, so a check can tell latitude from longitude.
"""

import os
from typing import Any

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, layer_kind

MAX_SUMMED_FEATURES = 1000
MAX_LISTED_POINTS = 5
POINT_DECIMALS = 4
NUMERIC_TYPES = ("int", "double", "real", "long", "decimal")


def snapshot(folder: str, before: set[str]) -> dict[str, Any]:
    project = QgsProject.instance()
    layers = {layer.name(): layer_state(layer, project) for layer in project.mapLayers().values()}
    return {
        "project": {
            "crs": project.crs().authid(),
            "layouts": [layout.name() for layout in project.layoutManager().layouts()],
            "annotations": _annotations(project),
            "annotation_texts": _annotation_texts(project),
        },
        "layers": layers,
        "files": sorted(_files(folder) - before),
    }


def files(folder: str) -> set[str]:
    return _files(folder)


def layer_state(layer: Any, project: QgsProject) -> dict[str, Any]:
    state: dict[str, Any] = {"kind": layer_kind(layer), "crs": crs_authid(layer)}
    node = project.layerTreeRoot().findLayer(layer.id())
    state["visible"] = bool(node.isVisible()) if node is not None else False
    if isinstance(layer, QgsVectorLayer):
        state.update(_vector(layer))
    elif isinstance(layer, QgsRasterLayer):
        renderer = layer.renderer()
        state["renderer"] = renderer.type() if renderer is not None else ""
        state["opacity"] = round(float(renderer.opacity()), 3) if renderer is not None else 1.0
    return state


def _vector(layer: QgsVectorLayer) -> dict[str, Any]:
    fields = layer.fields()
    count = int(layer.featureCount())
    state: dict[str, Any] = {
        "geometry": geometry_type_name(layer),
        "feature_count": count,
        "fields": [field.name() for field in fields],
        "opacity": round(float(layer.opacity()), 3),
        "labels": bool(layer.labelsEnabled()),
    }
    renderer = layer.renderer()
    if renderer is not None:
        state["renderer"] = renderer.type()
        if hasattr(renderer, "classAttribute"):
            state["class_attribute"] = renderer.classAttribute()
        if hasattr(renderer, "ranges"):
            state["classes"] = len(renderer.ranges())
        elif hasattr(renderer, "categories"):
            state["classes"] = len(renderer.categories())
    labeling = layer.labeling()
    settings = getattr(labeling, "settings", None)
    if layer.labelsEnabled() and callable(settings):
        state["label_field"] = settings().fieldName
    if count <= MAX_SUMMED_FEATURES:
        state["sums"] = _sums(layer)
        if state["geometry"] == "point" and count <= MAX_LISTED_POINTS:
            state["points_wgs84"] = _points(layer)
    return state


def _sums(layer: QgsVectorLayer) -> dict[str, float]:
    numeric = [field.name() for field in layer.fields() if field.typeName().lower().startswith(NUMERIC_TYPES)]
    sums = dict.fromkeys(numeric, 0.0)
    for feature in layer.getFeatures():
        for name in numeric:
            value = feature[name]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sums[name] += float(value)
    return {name: round(total, 3) for name, total in sums.items()}


def _points(layer: QgsVectorLayer) -> list[list[float]]:
    transform = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance().transformContext()
    )
    points = []
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        point = transform.transform(geometry.asPoint())
        points.append([round(point.x(), POINT_DECIMALS), round(point.y(), POINT_DECIMALS)])
    return points


def _annotations(project: QgsProject) -> int:
    try:
        return len(project.mainAnnotationLayer().items())
    except Exception:
        return 0


def _annotation_texts(project: QgsProject) -> list[str]:
    """The text notes' words: a marker in place of a note looked like success once (the text item crashed)."""
    try:
        items = project.mainAnnotationLayer().items().values()
    except Exception:
        return []
    return [str(item.text()) for item in items if hasattr(item, "text")]


def _files(folder: str) -> set[str]:
    found = set()
    for root, _dirs, names in os.walk(folder):
        for name in names:
            found.add(os.path.relpath(os.path.join(root, name), folder))
    return found
