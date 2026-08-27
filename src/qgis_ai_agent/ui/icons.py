from typing import Any, Callable

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap

CANVAS = 16.0
STROKE = 1.45
KNOB = 1.85
MAX_RATIO = 4.0


def sessions(colour: Any, size: int) -> QIcon:
    return _icon(_draw_clock, colour, size)


def clear(colour: Any, size: int) -> QIcon:
    return _icon(_draw_bin, colour, size)


def settings(colour: Any, size: int) -> QIcon:
    return _icon(_draw_sliders, colour, size)


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


def _draw_sliders(painter: QPainter) -> None:
    painter.drawLine(QPointF(2.7, 5.7), QPointF(13.3, 5.7))
    painter.drawLine(QPointF(2.7, 10.3), QPointF(13.3, 10.3))
    _knob(painter, 6.0, 5.7)
    _knob(painter, 10.2, 10.3)


def _knob(painter: QPainter, x: float, y: float) -> None:
    painter.setBrush(painter.pen().color())
    painter.drawEllipse(QPointF(x, y), KNOB, KNOB)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _icon(draw: Callable[[QPainter], None], colour: Any, size: int) -> QIcon:
    ratio = _ratio()
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(size * ratio / CANVAS, size * ratio / CANVAS)
        painter.setPen(_pen(colour))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        draw(painter)
    finally:
        painter.end()
    return QIcon(pixmap)


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
