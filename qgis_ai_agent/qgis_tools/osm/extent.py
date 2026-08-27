from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

WGS84 = "EPSG:4326"
PARTS = 4
MAX_DEGREES = 180.0
MAX_SPAN_DEGREES = 5.0
TOO_WIDE = (
    "The rectangle is wider than {span:.1f}° — Overpass usually refuses that much data. "
    "Narrow the extent down or give area with a place name instead."
)


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [item.strip() for item in str(text or "").replace(";", ",").split(",")]
    if len(parts) != PARTS:
        raise ValueError(f"bbox is given as four numbers \"west,south,east,north\" in degrees, got: '{text}'.")
    try:
        west, south, east, north = (float(item) for item in parts)
    except ValueError:
        raise ValueError(f"bbox '{text}' holds a value that is not a number.") from None
    return _checked(west, south, east, north)


def canvas_bbox() -> tuple[float, float, float, float]:
    rectangle, source = _canvas_extent()
    if rectangle is None:
        raise ValueError("The map is not available, so the current view cannot be read. Give bbox as numbers, or area.")
    if source is not None and source.authid() != WGS84:
        rectangle = _to_wgs84(rectangle, source)
    return _checked(rectangle.xMinimum(), rectangle.yMinimum(), rectangle.xMaximum(), rectangle.yMaximum())


def _canvas_extent() -> tuple[Any, Any]:
    try:
        from qgis.utils import iface

        canvas = iface.mapCanvas()
        return canvas.extent(), canvas.mapSettings().destinationCrs()
    except Exception:
        return None, None


def _to_wgs84(rectangle: Any, source: Any) -> Any:
    transform = QgsCoordinateTransform(source, QgsCoordinateReferenceSystem(WGS84), QgsProject.instance())
    return transform.transformBoundingBox(rectangle)


def _checked(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    if west >= east or south >= north:
        raise ValueError(
            "In bbox the west must be less than the east, and the south less than the north. "
            f"Got: west {west}, south {south}, east {east}, north {north}."
        )
    if max(abs(west), abs(east)) > MAX_DEGREES or max(abs(south), abs(north)) > 90.0:
        raise ValueError("The bbox coordinates fall outside the range of latitude and longitude.")
    span = max(east - west, north - south)
    if span > MAX_SPAN_DEGREES:
        raise ValueError(TOO_WIDE.format(span=MAX_SPAN_DEGREES))
    return west, south, east, north
