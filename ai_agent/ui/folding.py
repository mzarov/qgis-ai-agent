from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QEvent, QSize, QVariantAnimation
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QAbstractScrollArea, QWidget

from ai_agent.ui import icons, style
from ai_agent.ui.compass import cubic_bezier
from ai_agent.ui.transitions import animation

FOLD_MS = 220
TURN_MS = 160
EASING = (0.2, 0.7, 0.3, 1.0)
OPEN_DEGREES = 90.0
UNBOUNDED = 16777215


class Chevron(QWidget):
    def __init__(self, palette: Any, size: int, box: int = 0):
        super().__init__()
        side = box or size
        self.mark = ((side - size) / 2, (side + size) / 2)
        self._size = size
        self._icon = icons.drawn("collapsed", style.faint(palette), size)
        self.angle = 0.0
        self.setFixedSize(side, side)
        self._turn = animation(self, TURN_MS, self._step)

    def set_open(self, open_: bool, animate: bool = True) -> None:
        target = OPEN_DEGREES if open_ else 0.0
        self._turn.stop()
        if not animate or not self.isVisible():
            self._step(target)
            return
        self._turn.setStartValue(self.angle)
        self._turn.setEndValue(target)
        self._turn.start()

    def finish(self) -> None:
        if self._turn.state() == QVariantAnimation.State.Running:
            self._turn.stop()
            self._step(self._turn.endValue())

    def _step(self, angle: Any) -> None:
        self.angle = float(angle)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        if self._icon is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        half = self._size // 2
        painter.drawPixmap(-half, -half, self._icon.pixmap(self._size, self._size))
        painter.end()


class ClipBox(QWidget):
    def __init__(self, content: QWidget, step: Callable[[], None] = lambda: None):
        super().__init__()
        self.content = content
        content.setParent(self)
        content.installEventFilter(self)
        self._step_hook = step
        self.open = False
        self._from = 0
        self._to = 0
        self._animation = animation(self, FOLD_MS, self._step, self._done)
        self.setVisible(False)

    def natural_height(self, width: int = -1) -> int:
        width = self.width() if width < 0 else width
        if self.content.hasHeightForWidth() and width > 0:
            return max(0, self.content.heightForWidth(width))
        return max(0, self.content.sizeHint().height())

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.natural_height(width)

    def sizeHint(self) -> QSize:
        return QSize(self.content.sizeHint().width(), self.natural_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(self.content.minimumSizeHint().width(), 0)

    def resizeEvent(self, event: Any) -> None:
        self._place()
        super().resizeEvent(event)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.content and event.type() == QEvent.Type.LayoutRequest:
            self.follow()
        return False

    def follow(self) -> None:
        self.updateGeometry()
        self._place()

    def _place(self) -> None:
        self.content.setGeometry(0, 0, self.width(), self.natural_height())

    def set_open(self, open_: bool, animate: bool = True) -> None:
        if open_ == self.open and self._animation.state() != QVariantAnimation.State.Running:
            return
        self.open = open_
        self._animation.stop()
        if not animate or not self.window().isVisible():
            self._done()
            return
        self._from = self.height() if self.isVisible() else 0
        self.setMaximumHeight(self._from)
        self.setVisible(True)
        parent = self.parentWidget()
        width = self.width() or (parent.width() if parent is not None else 0)
        self._to = self.natural_height(width) if open_ else 0
        self._animation.start()

    def finish(self) -> None:
        if self._animation.state() == QVariantAnimation.State.Running:
            self._animation.stop()
            self._done()

    def _step(self, value: Any) -> None:
        progress = cubic_bezier(EASING, float(value))
        self.setMaximumHeight(round(self._from + (self._to - self._from) * progress))
        lay_out_above(self)
        self._step_hook()

    def _done(self) -> None:
        self.setMaximumHeight(UNBOUNDED)
        self.setVisible(self.open)
        self._step_hook()


def lay_out_above(widget: QWidget) -> None:
    # Qt passes a size change up one parent per event round; a frame painted between them jumps.
    parent = widget.parentWidget()
    while parent is not None and not parent.isWindow():
        viewport = _scroll_viewport(parent)
        if viewport is not None:
            # The area sizes its content first, or the feed squeezes every message below for a frame.
            QCoreApplication.sendEvent(viewport, QEvent(QEvent.Type.LayoutRequest))
        if isinstance(parent, ClipBox):
            parent.follow()
        elif parent.layout() is not None:
            parent.layout().activate()
        if viewport is not None:
            return
        parent = parent.parentWidget()


def _scroll_viewport(widget: QWidget) -> QWidget | None:
    viewport = widget.parentWidget()
    area = viewport.parentWidget() if viewport is not None else None
    if isinstance(area, QAbstractScrollArea) and area.viewport() is viewport:
        return viewport
    return None
