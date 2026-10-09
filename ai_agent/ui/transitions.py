"""The feed's transitions, after the design handoff's new conversation: what leaves rises, what comes rises in.

Whatever the feed showed — a conversation, the welcome — leaves as a snapshot
laid over the viewport, since the feed itself changes at once: it fades and
rises 8 px in 200 ms (CSS ease-in). Then what replaced it arrives: it fades in
and settles from 10 px below in 320 ms on cubic-bezier(.2,.7,.3,1). Three moments
play it: a new conversation (the welcome arrives, the line about the saved
conversation 120 ms behind), the first message on the welcome (the chat
arrives), and a conversation opened from the history. What arrives moves inside
a graphics effect, not through its layout, so nothing reflows while it plays.
Every animation is owned by its widget and ticks a bound method, so a widget
deleted mid-play takes its ticks with it.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QObject, QPoint, QRect, QRectF, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPixmap, QRegion
from qgis.PyQt.QtWidgets import QGraphicsEffect, QWidget

from ai_agent.ui.compass import cubic_bezier

LEAVE_MS = 200
LEAVE_RISE = 8
# CSS ease-in, the handoff's curve for the leaving conversation.
LEAVE_EASING = (0.42, 0.0, 1.0, 1.0)
ARRIVE_MS = 320
ARRIVE_DROP = 10
LAG_MS = 120
ARRIVE_EASING = (0.2, 0.7, 0.3, 1.0)


def arrival(elapsed_ms: float, delay_ms: float = 0.0) -> float:
    """How far an arriving part has come, 0…1 on the handoff's curve, for a part starting `delay_ms` late."""
    linear = (elapsed_ms - delay_ms) / ARRIVE_MS
    # Exact at both ends: the curve is solved numerically and would leave a trace of opacity.
    if linear <= 0.0:
        return 0.0
    if linear >= 1.0:
        return 1.0
    return cubic_bezier(ARRIVE_EASING, linear)


class LeavingFeed(QWidget):
    """A snapshot of the old conversation, fading and rising over the viewport; gone once it is done."""

    finished = pyqtSignal()

    def __init__(self, snapshot: QPixmap, parent: QWidget):
        super().__init__(parent)
        self._snapshot = snapshot
        self.progress = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(parent.rect())
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(LEAVE_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._step)
        self._animation.finished.connect(self._done)

    def start(self) -> None:
        self.show()
        self.raise_()
        self._animation.start()

    def finish(self) -> None:
        """Be gone at once, as a screenshot wants it; what waits for the leaving starts now."""
        self._animation.stop()
        self._done()

    def _step(self, value: Any) -> None:
        self.progress = cubic_bezier(LEAVE_EASING, float(value))
        self.update()

    def _done(self) -> None:
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setOpacity(1.0 - self.progress)
        painter.drawPixmap(0, round(-LEAVE_RISE * self.progress), self._snapshot)
        painter.end()


class ArrivalEffect(QGraphicsEffect):
    """Draws its widget fading in and settling from below; the `lagging` part, and all below it,
    follows LAG_MS behind. The widget stays where its layout put it the whole time."""

    def __init__(self, lagging: Callable[[], QRect | None], parent: Any = None):
        super().__init__(parent)
        self._lagging = lagging
        self.elapsed = 0.0

    def set_elapsed(self, elapsed: float) -> None:
        self.elapsed = elapsed
        self.update()

    def boundingRectFor(self, rect: QRectF) -> QRectF:
        # Drawn up to ARRIVE_DROP lower than the widget: its repaints must cover that strip too.
        return rect.adjusted(0, 0, 0, ARRIVE_DROP)

    def draw(self, painter: QPainter) -> None:
        pixmap, offset = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates)
        if pixmap.isNull():
            return
        ratio = pixmap.devicePixelRatio() or 1.0
        width, height = round(pixmap.width() / ratio), round(pixmap.height() / ratio)
        lagging = self._lagging()
        painter.save()
        if lagging is None or lagging.isEmpty():
            _paint(painter, pixmap, offset, arrival(self.elapsed))
        else:
            # Split at the top of the lagging line, the welcome's last row: all above it moves first.
            top, bottom = offset.y(), offset.y() + height + ARRIVE_DROP
            split = min(max(lagging.top(), top), bottom)
            above = QRegion(QRect(offset.x(), top, width, split - top))
            below = QRegion(QRect(offset.x(), split, width, bottom - split))
            painter.setClipRegion(above)
            _paint(painter, pixmap, offset, arrival(self.elapsed))
            painter.setClipRegion(below)
            _paint(painter, pixmap, offset, arrival(self.elapsed, LAG_MS))
        painter.restore()


class Arrival(QObject):
    """Holds `target` unseen behind an ArrivalEffect until `start`, plays it, then takes the effect off.

    Owned by the target, so it dies with it; it touches the effect only while the target still wears it.
    """

    def __init__(self, target: QWidget, lagging: Callable[[], QRect | None] = lambda: None):
        super().__init__(target)
        self._target = target
        self._effect = ArrivalEffect(lagging, target)
        target.setGraphicsEffect(self._effect)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(ARRIVE_MS + LAG_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(float(ARRIVE_MS + LAG_MS))
        self._animation.valueChanged.connect(self._tick)
        self._animation.finished.connect(self._done)

    def start(self) -> None:
        self._animation.start()

    def finish(self) -> None:
        """Arrive at once, as a screenshot wants it."""
        self._animation.stop()
        self._done()

    def _worn(self) -> bool:
        # Another effect may have replaced this one, and Qt deleted it then.
        return self._target.graphicsEffect() is self._effect

    def _tick(self, elapsed: Any) -> None:
        if self._worn():
            self._effect.set_elapsed(float(elapsed))

    def _done(self) -> None:
        if self._worn():
            # Without the effect the target paints directly again; Qt deletes the effect itself.
            self._target.setGraphicsEffect(None)
        self.deleteLater()


def leave(snapshot: QPixmap, viewport: QWidget, then: Callable[[], None]) -> None:
    """Lay `snapshot` over `viewport`, let it leave, then call `then` (a bound method, so it dies with its owner)."""
    overlay = LeavingFeed(snapshot, viewport)
    overlay.finished.connect(then)
    overlay.start()


def _paint(painter: QPainter, pixmap: QPixmap, offset: QPoint, progress: float) -> None:
    painter.setOpacity(progress)
    painter.drawPixmap(offset + QPoint(0, round(ARRIVE_DROP * (1.0 - progress))), pixmap)
