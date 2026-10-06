from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

from ai_agent.qgis_tools.common.layers import canvas_extent, find_layer_by_name

WGS84 = "EPSG:4326"
CANVAS = "canvas"
MAX_SPAN_DEGREES = 10.0
REGION_HINT = (
    'Give bbox as "west,south,east,north" in degrees, bbox="canvas" for the current map view, '
    "or layer_name to search over a layer's extent."
)


def region(params: dict[str, Any]) -> tuple[float, float, float, float]:
    """The search rectangle in degrees from bbox, the map view or a layer's extent."""
    raw = str(params.get("bbox") or "").strip()
    layer_name = str(params.get("layer_name") or "").strip()
    if raw and layer_name:
        raise ValueError("Give one of the two: bbox or layer_name — not both.")
    if layer_name:
        layer = find_layer_by_name(layer_name)
        return _checked(*_degrees(layer.extent(), layer.crs()))
    if raw.lower() == CANVAS:
        return _checked(*_degrees(canvas_extent(), _canvas_crs()))
    if raw:
        return _checked(*_numbers(raw))
    raise ValueError("No area was given. " + REGION_HINT)


def _numbers(text: str) -> tuple[float, float, float, float]:
    parts = [item.strip() for item in text.replace(";", ",").split(",")]
    try:
        west, south, east, north = (float(item) for item in parts)
    except ValueError:
        raise ValueError(f"bbox '{text}' is not four numbers. " + REGION_HINT) from None
    return west, south, east, north


def _degrees(rectangle: Any, crs: Any) -> tuple[float, float, float, float]:
    if crs is not None and crs.isValid() and crs.authid() != WGS84:
        transform = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem(WGS84), QgsProject.instance())
        rectangle = transform.transformBoundingBox(rectangle)
    return rectangle.xMinimum(), rectangle.yMinimum(), rectangle.xMaximum(), rectangle.yMaximum()


def _canvas_crs() -> Any:
    try:
        from qgis.utils import iface

        return iface.mapCanvas().mapSettings().destinationCrs()
    except Exception:
        return QgsProject.instance().crs()


def _checked(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    if west >= east or south >= north:
        raise ValueError(f"The area is empty or inverted: west {west}, south {south}, east {east}, north {north}.")
    if max(abs(west), abs(east)) > 180 or max(abs(south), abs(north)) > 90:
        raise ValueError("The area falls outside longitude and latitude. Is the layer's CRS set right?")
    if max(east - west, north - south) > MAX_SPAN_DEGREES:
        raise ValueError(
            f"The area is wider than {MAX_SPAN_DEGREES:.0f}°; scenes cover about 1°. Search a smaller area."
        )
    return west, south, east, north
