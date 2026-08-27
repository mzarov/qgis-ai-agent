from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

WGS84 = "EPSG:4326"
PARTS = 4
MAX_DEGREES = 180.0
MAX_SPAN_DEGREES = 5.0
TOO_WIDE = (
    "Прямоугольник шире {span:.1f}° — Overpass такой объём обычно не отдаёт. "
    "Сузьте охват или задайте area с именем места."
)


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [item.strip() for item in str(text or "").replace(";", ",").split(",")]
    if len(parts) != PARTS:
        raise ValueError(
            'bbox задаётся четырьмя числами "запад,юг,восток,север" в градусах, '
            f"получено: «{text}»."
        )
    try:
        west, south, east, north = (float(item) for item in parts)
    except ValueError:
        raise ValueError(f"В bbox «{text}» есть значение, которое не число.")
    return _checked(west, south, east, north)


def canvas_bbox() -> tuple[float, float, float, float]:
    rectangle, source = _canvas_extent()
    if rectangle is None:
        raise ValueError(
            "Карта недоступна, текущий вид взять неоткуда. Задайте bbox числами или area."
        )
    if source is not None and source.authid() != WGS84:
        rectangle = _to_wgs84(rectangle, source)
    return _checked(
        rectangle.xMinimum(), rectangle.yMinimum(), rectangle.xMaximum(), rectangle.yMaximum()
    )


def _canvas_extent() -> tuple[Any, Any]:
    try:
        from qgis.utils import iface

        canvas = iface.mapCanvas()
        return canvas.extent(), canvas.mapSettings().destinationCrs()
    except Exception:
        return None, None


def _to_wgs84(rectangle: Any, source: Any) -> Any:
    transform = QgsCoordinateTransform(
        source, QgsCoordinateReferenceSystem(WGS84), QgsProject.instance()
    )
    return transform.transformBoundingBox(rectangle)


def _checked(
    west: float, south: float, east: float, north: float
) -> tuple[float, float, float, float]:
    if west >= east or south >= north:
        raise ValueError(
            "В bbox запад должен быть меньше востока, а юг меньше севера. "
            f"Получено: запад {west}, юг {south}, восток {east}, север {north}."
        )
    if max(abs(west), abs(east)) > MAX_DEGREES or max(abs(south), abs(north)) > 90.0:
        raise ValueError("Координаты bbox выходят за пределы градусов широты и долготы.")
    span = max(east - west, north - south)
    if span > MAX_SPAN_DEGREES:
        raise ValueError(TOO_WIDE.format(span=MAX_SPAN_DEGREES))
    return west, south, east, north
