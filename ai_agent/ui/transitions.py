from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QVariantAnimation, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPixmap, QRegion
from qgis.PyQt.QtWidgets import QGraphicsEffect, QWidget

from ai_agent.ui.compass import cubic_bezier

LEAVE_MS = 200
LEAVE_RISE = 8
LEAVE_EASING = (0.42, 0.0, 1.0, 1.0)
ARRIVE_MS = 320
ARRIVE_DROP = 10
LAG_MS = 120
ARRIVE_EASING = (0.2, 0.7, 0.3, 1.0)
MENU_MS = 140
MENU_DROP = 4
MENU_EASING = (0.25, 0.1, 0.25, 1.0)


def animation(
    owner: QObject, ms: int, step: Callable[[Any], None], done: Callable[[], None] | None = None, end: float = 1.0
) -> QVariantAnimation:
    # `step` and `done` must be bound methods: Qt drops those with their widget, a lambda outlives it.
    motion = QVariantAnimation(owner)
    motion.setDuration(ms)
    motion.setStartValue(0.0)
    motion.setEndValue(end)
    motion.valueChanged.connect(step)
    if done is not None:
        motion.finished.connect(done)
    return motion


def arrival(elapsed_ms: float, delay_ms: float = 0.0) -> float:
    linear = (elapsed_ms - delay_ms) / ARRIVE_MS
    if linear <= 0.0:
        return 0.0
    if linear >= 1.0:
        return 1.0
    return cubic_bezier(ARRIVE_EASING, linear)


class LeavingFeed(QWidget):
    finished = pyqtSignal()

    def __init__(self, snapshot: QPixmap, parent: QWidget):
        super().__init__(parent)
        self._snapshot = snapshot
        self.progress = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(parent.rect())
        self._animation = animation(self, LEAVE_MS, self._step, self._done)

    def start(self) -> None:
        self.show()
        self.raise_()
        self._animation.start()

    def finish(self) -> None:
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
    def __init__(self, target: QWidget, lagging: Callable[[], QRect | None]):
        super().__init__(target)
        self._target = target
        self._lagging = lagging
        self.elapsed = 0.0

    def set_elapsed(self, elapsed: float) -> None:
        self.elapsed = elapsed
        self.update()

    def boundingRectFor(self, rect: QRectF) -> QRectF:
        # Drawn up to ARRIVE_DROP lower than the widget: its repaints must cover that strip too.
        return rect.adjusted(0, 0, 0, ARRIVE_DROP)

    def draw(self, painter: QPainter) -> None:
        # What shows, and the strip the drop uncovers: sourcePixmap renders a long feed whole on every frame.
        shown = self._target.visibleRegion().boundingRect().adjusted(0, -ARRIVE_DROP, 0, 0) & self._target.rect()
        if shown.isEmpty():
            return
        ratio = painter.device().devicePixelRatio() or 1.0
        pixmap = QPixmap(shown.size() * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        self._target.render(pixmap, QPoint(), QRegion(shown), QWidget.RenderFlag.DrawChildren)
        offset, width, height = shown.topLeft(), shown.width(), shown.height()
        lagging = self._lagging()
        painter.save()
        if lagging is None or lagging.isEmpty():
            _paint(painter, pixmap, offset, arrival(self.elapsed))
        else:
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
    def __init__(self, target: QWidget, lagging: Callable[[], QRect | None] = lambda: None):
        super().__init__(target)
        self._target = target
        self._effect = ArrivalEffect(target, lagging)
        target.setGraphicsEffect(self._effect)
        total = ARRIVE_MS + LAG_MS
        self._animation = animation(self, total, self._tick, self._done, end=float(total))

    def start(self) -> None:
        self._animation.start()

    def finish(self) -> None:
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


# Moves the window: over a menu's style-drawn rows a graphics effect would show a snapshot.
class DropIn(QObject):
    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._target = QPoint()
        self._animation = animation(self, MENU_MS, self._tick, self._settle)
        window.installEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self._window:
            kind = event.type()
            if kind == QEvent.Type.Show:
                self._target = self._window.pos()
                self._animation.stop()
                self._tick(0.0)
                self._animation.start()
            elif kind == QEvent.Type.Hide:
                self._animation.stop()
                self._window.setWindowOpacity(1.0)
        return False

    def _tick(self, value: Any) -> None:
        progress = cubic_bezier(MENU_EASING, min(max(float(value), 0.0), 1.0))
        self._window.setWindowOpacity(progress)
        self._window.move(self._target.x(), self._target.y() - round(MENU_DROP * (1.0 - progress)))

    def _settle(self) -> None:
        self._window.setWindowOpacity(1.0)
        self._window.move(self._target)


def leave(snapshot: QPixmap, viewport: QWidget, then: Callable[[], None]) -> None:
    # `then` must be a bound method, so it dies with its owner.
    overlay = LeavingFeed(snapshot, viewport)
    overlay.finished.connect(then)
    overlay.start()


def _paint(painter: QPainter, pixmap: QPixmap, offset: QPoint, progress: float) -> None:
    painter.setOpacity(progress)
    painter.drawPixmap(offset + QPoint(0, round(ARRIVE_DROP * (1.0 - progress))), pixmap)
