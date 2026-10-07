"""The brand mark: a compass with an open ring whose needle says what the agent is doing.

Geometry on a 24-unit grid centred at (12, 12), from the design handoff. The
ring is an arc of radius 8.5 with a 60° gap around north-east; the needle is
drawn pointing north and rotated about the centre. A diamond of the colour
under the mark (the "halo") cuts the ring where the needle crosses it, so the
needle reads in any position. Line weights are optical: heavier at small sizes.

States are rotations of the needle only, keyframed like the prototype's CSS:
each segment between two keyframes has its own easing, so the swing matches.
One live compass per panel — in the status line; marks elsewhere stay still.
"""

import math
from dataclasses import dataclass
from typing import Any

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation
from qgis.PyQt.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

from ai_agent.ui import style

GRID = 24.0
CENTRE = 12.0
RING_RECT = QRectF(3.5, 3.5, 17.0, 17.0)
# The arc runs clockwise from 15° to 75° the long way round (Qt measures counter-clockwise from 3 o'clock).
RING_START = 15.0
RING_SWEEP = -300.0
HALO = ((12.0, 1.2), (14.7, 12.0), (12.0, 18.6), (9.3, 12.0))
SOUTH = ((9.9, 12.0), (14.1, 12.0), (12.0, 17.7))
NORTH = ((12.0, 1.6), (14.5, 12.0), (9.5, 12.0))
AXIS_RADIUS = 0.9
# Ring and needle-outline widths in grid units, by the size the mark is drawn at.
SMALL, MEDIUM = 16, 30
WEIGHTS = {SMALL: (2.6, 1.7), MEDIUM: (2.2, 1.5)}
LARGE_WEIGHTS = (1.9, 1.3)
HALO_EXTRA = 0.4

REST = "rest"
NORTH_STATE = "north"
SEARCH = "search"
DONE = "done"
ERROR = "error"
ASK = "ask"
ARRIVE = "arrive"

EASE_IN_OUT = (0.42, 0.0, 0.58, 1.0)
SETTLE = (0.3, 0.7, 0.3, 1.0)
LINEAR = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class Motion:
    """Keyframes as (fraction, degrees), the cycle length, whether it repeats, and each segment's easing."""

    keys: tuple[tuple[float, float], ...]
    milliseconds: int
    loops: bool
    easing: tuple[float, float, float, float]


MOTIONS = {
    SEARCH: Motion(((0, 18), (0.22, 82), (0.46, 28), (0.72, 66), (1, 18)), 3200, True, EASE_IN_OUT),
    DONE: Motion(((0, 45), (0.28, -12), (0.44, 6), (0.58, -2), (0.68, 0), (1, 0)), 1600, False, SETTLE),
    ERROR: Motion(
        ((0, 45), (0.06, 34), (0.12, 56), (0.18, 38), (0.24, 51), (0.3, 42), (0.36, 45), (1, 45)), 2200, False, LINEAR
    ),
    ASK: Motion(((0, 30), (0.5, 60), (1, 30)), 3000, True, EASE_IN_OUT),
    ARRIVE: Motion(((0, -140), (0.55, 62), (0.75, 39), (0.9, 47), (1, 45)), 1100, False, SETTLE),
}
RESTING = {REST: 45.0, NORTH_STATE: 0.0}


def cubic_bezier(easing: tuple[float, float, float, float], progress: float) -> float:
    """CSS cubic-bezier timing: the curve's y where its x equals `progress`."""
    x1, y1, x2, y2 = easing

    def axis(t: float, first: float, second: float) -> float:
        return 3 * (1 - t) ** 2 * t * first + 3 * (1 - t) * t**2 * second + t**3

    low, high = 0.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if axis(middle, x1, x2) < progress:
            low = middle
        else:
            high = middle
    return axis((low + high) / 2, y1, y2)


def angle_at(state: str, progress: float) -> float:
    """The needle's rotation in degrees at `progress` (0…1) through the state's motion."""
    if state in RESTING:
        return RESTING[state]
    motion = MOTIONS.get(state)
    if motion is None:
        return RESTING[REST]
    progress = min(max(progress, 0.0), 1.0)
    for (start, first), (end, second) in zip(motion.keys, motion.keys[1:], strict=False):
        if progress <= end:
            span = end - start
            local = (progress - start) / span if span else 1.0
            return first + (second - first) * cubic_bezier(motion.easing, local)
    return motion.keys[-1][1]


def end_angle(state: str) -> float:
    """Where a state leaves the needle: a motion's last keyframe, or the resting angle."""
    motion = MOTIONS.get(state)
    return motion.keys[-1][1] if motion is not None else RESTING.get(state, RESTING[REST])


def weights(size: float) -> tuple[float, float]:
    if size <= SMALL:
        return WEIGHTS[SMALL]
    if size <= MEDIUM:
        return WEIGHTS[MEDIUM]
    return LARGE_WEIGHTS


@dataclass(frozen=True)
class Colours:
    ring: QColor
    needle: QColor
    halo: QColor


def paint(painter: QPainter, rect: QRectF, angle: float, colours: Colours) -> None:
    """Draw the mark into `rect` (square) with the needle at `angle` degrees clockwise from north."""
    size = min(rect.width(), rect.height())
    ring_width, outline = weights(size)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x() - size / 2, rect.center().y() - size / 2)
    painter.scale(size / GRID, size / GRID)
    ring = QPainterPath()
    ring.arcMoveTo(RING_RECT, RING_START)
    ring.arcTo(RING_RECT, RING_START, RING_SWEEP)
    painter.setPen(_pen(colours.ring, ring_width))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(ring)
    painter.translate(CENTRE, CENTRE)
    painter.rotate(angle)
    painter.translate(-CENTRE, -CENTRE)
    painter.setPen(_pen(colours.halo, ring_width + HALO_EXTRA))
    painter.setBrush(QBrush(colours.halo))
    painter.drawPolygon(_polygon(HALO))
    painter.setPen(_pen(colours.ring, outline))
    painter.drawPolygon(_polygon(SOUTH))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(colours.needle))
    painter.drawPolygon(_polygon(NORTH))
    if size > SMALL:
        painter.setBrush(QBrush(colours.halo))
        painter.drawEllipse(QPointF(CENTRE, CENTRE), AXIS_RADIUS, AXIS_RADIUS)
    painter.restore()


def pixmap(size: int, colours: Colours, angle: float = RESTING[REST], ratio: float = 1.0) -> QPixmap:
    """A still mark for icons and headers, drawn at the screen's pixel ratio."""
    image = QPixmap(int(math.ceil(size * ratio)), int(math.ceil(size * ratio)))
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint(painter, QRectF(0, 0, size, size), angle, colours)
    painter.end()
    return image


def colours_for(palette: Any, halo: QColor | None = None, failed: bool = False) -> Colours:
    needle = style.danger(palette) if failed else style.accent(palette)
    return Colours(style.text(palette), needle, halo if halo is not None else style.background(palette))


class Compass(QWidget):
    """The live mark: `set_state` plays a state's motion; repeating ones run until the next state."""

    def __init__(self, size: int, palette: Any, halo: QColor | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self._palette = palette
        self._halo = halo
        self.state = REST
        self.angle = RESTING[REST]
        self._motion: Any = None
        self.setFixedSize(QSize(size, size))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_state(self, state: str) -> None:
        if self._motion is not None:
            self._motion.stop()
            self._motion = None
        self.state = state
        motion = MOTIONS.get(state)
        if motion is None:
            self._turn(RESTING.get(state, RESTING[REST]))
            return
        animation = QVariantAnimation(self)
        animation.setDuration(motion.milliseconds)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setLoopCount(-1 if motion.loops else 1)
        # A bound method, not a lambda: Qt drops the connection when the widget dies, so a tick
        # arriving while the feed deletes the widget cannot reach a half-destroyed object.
        animation.valueChanged.connect(self._on_progress)
        self._motion = animation
        self._turn(angle_at(state, 0.0))
        animation.start()

    def stop(self) -> None:
        """Freeze where the state ends: a still widget costs no repaints."""
        if self._motion is not None:
            self._motion.stop()
            self._motion = None
        motion = MOTIONS.get(self.state)
        self._turn(RESTING[REST] if motion is not None and motion.loops else end_angle(self.state))

    def _on_progress(self, progress: Any) -> None:
        self._turn(angle_at(self.state, float(progress)))

    def _turn(self, angle: float) -> None:
        self.angle = angle
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        paint(
            painter,
            QRectF(0, 0, self._size, self._size),
            self.angle,
            colours_for(self._palette, self._halo, failed=self.state == ERROR),
        )
        painter.end()


def _pen(colour: QColor, width: float) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _polygon(points: tuple[tuple[float, float], ...]) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])
