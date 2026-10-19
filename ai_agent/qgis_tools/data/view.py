from typing import Any

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMessageLog,
    QgsProject,
    QgsRectangle,
)

WGS84 = "EPSG:4326"
VIEW_TOO_WIDE = 25.0

Box = tuple[float, ...]


def needs_move(view: Box | None, coverage: Box) -> bool:
    if view is None:
        return True
    west, south, east, north = coverage
    overlap_x = min(view[2], east) - max(view[0], west)
    overlap_y = min(view[3], north) - max(view[1], south)
    if overlap_x <= 0 or overlap_y <= 0:
        return True
    view_area = (view[2] - view[0]) * (view[3] - view[1])
    return view_area > VIEW_TOO_WIDE * (east - west) * (north - south)


def show_coverage(coverage: Box) -> bool:
    if not coverage:
        return False
    try:
        from qgis.utils import iface

        canvas = iface.mapCanvas() if iface else None
        if canvas is None:
            return False
        project = QgsProject.instance()
        to_map = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem(WGS84), canvas.mapSettings().destinationCrs(), project
        )
        if not needs_move(_view(canvas, to_map), coverage):
            return False
        canvas.setExtent(to_map.transformBoundingBox(QgsRectangle(*coverage)))
        canvas.refresh()
        return True
    except Exception as error:
        QgsMessageLog.logMessage(
            f"Could not move the map to the service: {error}", "AI Agent", Qgis.MessageLevel.Warning
        )
        return False


def _view(canvas: Any, to_map: Any) -> Box | None:
    try:
        extent = to_map.transformBoundingBox(canvas.extent(), Qgis.TransformDirection.Reverse)
    except Exception:
        return None
    box = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    if not all(abs(value) < float("inf") for value in box) or box[0] >= box[2] or box[1] >= box[3]:
        return None
    return box
