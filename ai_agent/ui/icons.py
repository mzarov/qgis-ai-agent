import math
from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap

CANVAS = 16.0
CENTRE = 8.0
STROKE = 1.45
MAX_RATIO = 4.0
GEAR_HUB = 1.85
GEAR_RING = 4.4
GEAR_TOOTH = 2.05
GEAR_TEETH = 8


def sessions(colour: Any, size: int) -> QIcon:
    return _icon(_draw_clock, colour, size)


def clear(colour: Any, size: int) -> QIcon:
    return _icon(_draw_bin, colour, size)


def settings(colour: Any, size: int) -> QIcon:
    return _icon(_draw_gear, colour, size)


def connection(colour: Any, size: int) -> QIcon:
    return _icon(_draw_plug, colour, size)


def privacy(colour: Any, size: int) -> QIcon:
    return _icon(_draw_shield, colour, size)


def skills(colour: Any, size: int) -> QIcon:
    return _icon(_draw_book, colour, size)


def geocoding(colour: Any, size: int) -> QIcon:
    return _icon(_draw_pin, colour, size)


def advanced(colour: Any, size: int) -> QIcon:
    return _icon(_draw_sliders, colour, size)


def brand(colour: Any, size: int) -> QIcon:
    return _icon(_draw_sparkle, colour, size)


def layer(colour: Any, size: int) -> QIcon:
    return _icon(_draw_layers, colour, size)


def _draw_clock(painter: QPainter) -> None:
    painter.drawEllipse(QRectF(2.0, 2.0, 12.0, 12.0))
    painter.drawLine(QPointF(8.0, 8.0), QPointF(8.0, 4.7))
    painter.drawLine(QPointF(8.0, 8.0), QPointF(10.5, 9.4))


def _draw_bin(painter: QPainter) -> None:
    painter.drawLine(QPointF(3.0, 4.7), QPointF(13.0, 4.7))
    handle = QPainterPath(QPointF(6.3, 4.7))
    handle.lineTo(6.3, 3.1)
    handle.lineTo(9.7, 3.1)
    handle.lineTo(9.7, 4.7)
    painter.drawPath(handle)
    body = QPainterPath(QPointF(4.5, 6.0))
    body.lineTo(5.3, 13.3)
    body.lineTo(10.7, 13.3)
    body.lineTo(11.5, 6.0)
    painter.drawPath(body)


def _draw_gear(painter: QPainter) -> None:
    centre = QPointF(CENTRE, CENTRE)
    painter.drawEllipse(centre, GEAR_RING, GEAR_RING)
    painter.drawEllipse(centre, GEAR_HUB, GEAR_HUB)
    for index in range(GEAR_TEETH):
        painter.drawLine(_at(index, GEAR_RING), _at(index, GEAR_RING + GEAR_TOOTH))


def tooth_at(index: int, radius: float) -> tuple[float, float]:
    angle = 2.0 * math.pi * index / GEAR_TEETH
    return CENTRE + radius * math.cos(angle), CENTRE + radius * math.sin(angle)


def tooth_gap(size: int) -> float:
    return 2.0 * math.pi * (GEAR_RING + GEAR_TOOTH) / GEAR_TEETH * scale_for(size)


def _at(index: int, radius: float) -> QPointF:
    x, y = tooth_at(index, radius)
    return QPointF(x, y)


def _icon(draw: Callable[[QPainter], None], colour: Any, size: int) -> QIcon:
    ratio = _ratio()
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(scale_for(size), scale_for(size))
        painter.setPen(_pen(colour))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        draw(painter)
    finally:
        painter.end()
    return QIcon(pixmap)


def scale_for(size: int) -> float:
    return size / CANVAS


def _pen(colour: Any) -> QPen:
    pen = QPen(colour)
    pen.setWidthF(STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _ratio() -> float:
    try:
        found = float(QGuiApplication.primaryScreen().devicePixelRatio())
    except Exception:
        return 1.0
    if found < 1.0 or found > MAX_RATIO:
        return 1.0
    return found


def _draw_plug(painter: QPainter) -> None:
    painter.drawLine(QPointF(6.0, 2.0), QPointF(6.0, 4.7))
    painter.drawLine(QPointF(10.0, 2.0), QPointF(10.0, 4.7))
    body = QPainterPath(QPointF(4.0, 4.7))
    body.lineTo(12.0, 4.7)
    body.lineTo(12.0, 7.3)
    body.cubicTo(QPointF(12.0, 9.7), QPointF(10.2, 11.3), QPointF(8.0, 11.3))
    body.cubicTo(QPointF(5.8, 11.3), QPointF(4.0, 9.7), QPointF(4.0, 7.3))
    body.closeSubpath()
    painter.drawPath(body)
    painter.drawLine(QPointF(8.0, 11.3), QPointF(8.0, 14.0))


def _draw_shield(painter: QPainter) -> None:
    outline = QPainterPath(QPointF(8.0, 2.0))
    outline.lineTo(13.3, 4.0)
    outline.lineTo(13.3, 8.0)
    outline.cubicTo(QPointF(13.3, 11.3), QPointF(11.0, 13.3), QPointF(8.0, 14.0))
    outline.cubicTo(QPointF(5.0, 13.3), QPointF(2.7, 11.3), QPointF(2.7, 8.0))
    outline.lineTo(2.7, 4.0)
    outline.closeSubpath()
    painter.drawPath(outline)
    tick = QPainterPath(QPointF(6.0, 8.0))
    tick.lineTo(7.4, 9.4)
    tick.lineTo(10.0, 6.8)
    painter.drawPath(tick)


def _draw_book(painter: QPainter) -> None:
    cover = QPainterPath(QPointF(3.0, 13.3))
    cover.lineTo(3.0, 3.7)
    cover.quadTo(QPointF(3.0, 2.3), QPointF(4.3, 2.3))
    cover.lineTo(13.0, 2.3)
    cover.lineTo(13.0, 12.3)
    cover.lineTo(4.3, 12.3)
    cover.quadTo(QPointF(3.0, 12.3), QPointF(3.0, 13.3))
    painter.drawPath(cover)
    painter.drawLine(QPointF(6.0, 5.3), QPointF(10.0, 5.3))


def _draw_pin(painter: QPainter) -> None:
    drop = QPainterPath(QPointF(8.0, 14.0))
    drop.cubicTo(QPointF(8.0, 14.0), QPointF(12.7, 9.9), QPointF(12.7, 6.3))
    drop.cubicTo(QPointF(12.7, 3.7), QPointF(10.6, 1.6), QPointF(8.0, 1.6))
    drop.cubicTo(QPointF(5.4, 1.6), QPointF(3.3, 3.7), QPointF(3.3, 6.3))
    drop.cubicTo(QPointF(3.3, 9.9), QPointF(8.0, 14.0), QPointF(8.0, 14.0))
    painter.drawPath(drop)
    painter.drawEllipse(QPointF(8.0, 6.3), 1.7, 1.7)


def _draw_sliders(painter: QPainter) -> None:
    for y, knob in ((4.0, 10.7), (8.0, 6.0), (12.0, 11.3)):
        painter.drawLine(QPointF(2.7, y), QPointF(knob - 1.4, y))
        painter.drawLine(QPointF(knob + 1.4, y), QPointF(13.3, y))
        painter.drawEllipse(QPointF(knob, y), 1.4, 1.4)


def _draw_sparkle(painter: QPainter) -> None:
    painter.drawPath(_star(8.0, 6.3, 4.3, 1.2))
    painter.drawPath(_star(12.6, 12.0, 2.0, 0.55))


def _draw_layers(painter: QPainter) -> None:
    top = QPainterPath(QPointF(2.7, 5.3))
    top.lineTo(8.0, 2.7)
    top.lineTo(13.3, 5.3)
    top.lineTo(8.0, 8.0)
    top.closeSubpath()
    painter.drawPath(top)
    for y in (8.3, 11.0):
        sheet = QPainterPath(QPointF(2.7, y))
        sheet.lineTo(8.0, y + 2.7)
        sheet.lineTo(13.3, y)
        painter.drawPath(sheet)


def _star(x: float, y: float, reach: float, waist: float) -> QPainterPath:
    """A four-pointed star: points at `reach`, the waist between them at `waist`."""
    path = QPainterPath(QPointF(x, y - reach))
    path.lineTo(x + waist, y - waist)
    path.lineTo(x + reach, y)
    path.lineTo(x + waist, y + waist)
    path.lineTo(x, y + reach)
    path.lineTo(x - waist, y + waist)
    path.lineTo(x - reach, y)
    path.lineTo(x - waist, y - waist)
    path.closeSubpath()
    return path
