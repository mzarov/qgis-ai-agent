"""What a task left in the project, as plain data a check can match: layers, project settings, files.

Only facts a request can change and a person would look at: a layer's geometry,
size, fields and their numeric sums (virtual fields too), its renderer and the
field it classifies by, labels, opacity, visibility; the project CRS, layouts
with the kinds of items they hold, and annotations; the files the run wrote into
the task's folder. Point layers of a few features also list their points in
EPSG:4326, so a check can tell latitude from longitude. Polygon layers carry
their total area on the WGS 84 ellipsoid, whatever their CRS: a buffer drawn in
Web Mercator "metres" has the right feature count and the wrong size.
"""

import os
from typing import Any

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, layer_kind

MAX_SUMMED_FEATURES = 1000
MAX_LISTED_POINTS = 5
POINT_DECIMALS = 4
AREA_DECIMALS = 3
SQUARE_METRES_PER_KM2 = 1_000_000
MEASURING_ELLIPSOID = "EPSG:7030"
LAYOUT_ITEM_PREFIX = "QgsLayoutItem"


def snapshot(folder: str, before: set[str], layers_before: dict[str, str]) -> dict[str, Any]:
    """The project now, against the folder's files and the layers' names by id (`layer_names`) before the task.

    Layers are told apart by id, never by name: a renamed layer stays under the
    name it began with, and a new layer that takes an old one's name is still new.
    """
    project = QgsProject.instance()
    layers = {
        layer_id: {"name": layer.name(), **layer_state(layer, project)}
        for layer_id, layer in project.mapLayers().items()
    }
    return {
        "project": {
            "crs": project.crs().authid(),
            "layouts": [layout.name() for layout in project.layoutManager().layouts()],
            "layout_items": _layout_items(project),
            "annotations": _annotations(project),
            "annotation_texts": _annotation_texts(project),
        },
        "layers": {layers_before[layer_id]: layer for layer_id, layer in layers.items() if layer_id in layers_before},
        "new_layers": [layer for layer_id, layer in layers.items() if layer_id not in layers_before],
        "files": sorted(_files(folder) - before),
    }


def files(folder: str) -> set[str]:
    return _files(folder)


def layer_names() -> dict[str, str]:
    return {layer_id: layer.name() for layer_id, layer in QgsProject.instance().mapLayers().items()}


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
        symbol = renderer.symbol() if hasattr(renderer, "symbol") else None
        if symbol is not None:
            # A single symbol made half transparent is a half transparent layer to the eye, as the layer's
            # own opacity is: a task about transparency accepts either.
            state["symbol_opacity"] = round(float(symbol.opacity()), 3)
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
        if state["geometry"] == "polygon":
            state["measured_km2"] = _area_km2(layer)
    return state


def _sums(layer: QgsVectorLayer) -> dict[str, float]:
    # By the field's type, not its type name: a virtual field's name is whatever its expression made it.
    numeric = [field.name() for field in layer.fields() if field.isNumeric()]
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
        # asPoint() refuses a multipoint: its points are its parts.
        for part in geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]:
            point = transform.transform(part)
            points.append([round(point.x(), POINT_DECIMALS), round(point.y(), POINT_DECIMALS)])
    return points


def _area_km2(layer: QgsVectorLayer) -> float:
    measure = QgsDistanceArea()
    measure.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
    measure.setEllipsoid(MEASURING_ELLIPSOID)
    total = 0.0
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry is not None and not geometry.isEmpty():
            total += measure.measureArea(geometry)
    return round(total / SQUARE_METRES_PER_KM2, AREA_DECIMALS)


def _layout_items(project: QgsProject) -> list[str]:
    """The kinds of items across all layouts: map, legend, label, scalebar…"""
    kinds = set()
    for layout in project.layoutManager().layouts():
        for item in layout.items():
            name = type(item).__name__
            if name.startswith(LAYOUT_ITEM_PREFIX) and len(name) > len(LAYOUT_ITEM_PREFIX):
                kinds.add(name[len(LAYOUT_ITEM_PREFIX) :].lower())
    return sorted(kinds)


def _annotations(project: QgsProject) -> int:
    try:
        return len(project.mainAnnotationLayer().items())
    except Exception:
        return 0


def _annotation_texts(project: QgsProject) -> list[str]:
    """The text notes' words, so a marker in place of a note does not pass for one."""
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
