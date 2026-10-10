"""Folding in the feed: a chevron that turns and a body that opens to its height, both animated.

The activity list and a reasoning block open the same way: the chevron turns a
quarter circle and the body grows from nothing to its full height (or shrinks
back) on the handoff's curve. The body is a `ClipBox`: its content keeps its
full height and the box only shows as much of it as the fold allows — a layout
given less room squeezed the rows mid-fold until they overlapped, and the user
saw the list jump. Every frame lays out the containers above the body at once:
Qt passes a size change up one parent per round of posted events, and a frame
painted between rounds showed the body grown inside parents that had not — the
fold stalled a frame or two, then jumped. Off screen, or asked to, the change is
immediate. The animations belong to their widgets and tick bound methods, so a
widget deleted mid-fold takes its ticks with it.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QEvent, QObject, QSize, QVariantAnimation
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QAbstractScrollArea, QWidget

from ai_agent.ui import icons, style
from ai_agent.ui.compass import cubic_bezier

FOLD_MS = 220
TURN_MS = 160
# The handoff's settle curve, as the transitions use it.
EASING = (0.2, 0.7, 0.3, 1.0)
OPEN_DEGREES = 90.0
# QWIDGETSIZE_MAX: no maximum height, once a body is open.
UNBOUNDED = 16777215


class Chevron(QWidget):
    """A chevron pointing right when folded and down when open, turning between the two."""

    def __init__(self, palette: Any, size: int, box: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        side = box or size
        # Where the drawing sits in the box, top to bottom: a timeline stops its line short of it.
        self.mark = ((side - size) / 2, (side + size) / 2)
        self._size = size
        self._icon = icons.drawn("collapsed", style.faint(palette), size)
        self.angle = 0.0
        self.setFixedSize(box or size, box or size)
        self._turn = QVariantAnimation(self)
        self._turn.setDuration(TURN_MS)
        self._turn.valueChanged.connect(self._step)

    def set_open(self, open_: bool, animate: bool = True) -> None:
        target = OPEN_DEGREES if open_ else 0.0
        self._turn.stop()
        if not animate or not self.isVisible():
            self._step_to(target)
            return
        self._turn.setStartValue(self.angle)
        self._turn.setEndValue(target)
        self._turn.start()

    def finish(self) -> None:
        if self._turn.state() == QVariantAnimation.State.Running:
            self._turn.stop()
            self._step_to(float(self._turn.endValue()))

    def _step(self, value: Any) -> None:
        self._step_to(float(value))

    def _step_to(self, angle: float) -> None:
        self.angle = angle
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
    """Holds `content` at its natural height and shows as much of it as its own height allows."""

    def __init__(self, content: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.content = content
        content.setParent(self)
        # The content's layout asks for room when rows come or grow: the box follows.
        content.installEventFilter(self)

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
        # As low as nothing: the fold decides the height, the content is clipped, never squeezed.
        return QSize(self.content.minimumSizeHint().width(), 0)

    def resizeEvent(self, event: Any) -> None:
        self._place()
        super().resizeEvent(event)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.content and event.type() == QEvent.Type.LayoutRequest:
            self.follow()
        return False

    def follow(self) -> None:
        """Take the content's new height now, instead of on its posted layout request."""
        self.updateGeometry()
        self._place()

    def _place(self) -> None:
        self.content.setGeometry(0, 0, self.width(), self.natural_height())


def lay_out_above(widget: QWidget) -> None:
    """Lay out every container above `widget` now, innermost first, up to the scroll area it sits in.

    Each layout fits its old size, then asks its parent for room, and the parent's turn resizes
    it: when the walk ends the whole chain holds the new size, before anything paints.
    """
    parent = widget.parentWidget()
    while parent is not None and not parent.isWindow():
        viewport = _scroll_viewport(parent)
        if viewport is not None:
            # The area sizes its content first: laid out in its old height, the feed squeezed
            # every message below for a moment, and each one laid its text out twice.
            QCoreApplication.sendEvent(viewport, QEvent(QEvent.Type.LayoutRequest))
        if isinstance(parent, ClipBox):
            parent.follow()
        elif parent.layout() is not None:
            parent.layout().activate()
        if viewport is not None:
            return
        parent = parent.parentWidget()


def _scroll_viewport(widget: QWidget) -> QWidget | None:
    """The viewport `widget` scrolls in, when it is a scroll area's content."""
    viewport = widget.parentWidget()
    area = viewport.parentWidget() if viewport is not None else None
    if isinstance(area, QAbstractScrollArea) and area.viewport() is viewport:
        return viewport
    return None


class Fold(QObject):
    """Opens and closes `body` by animating its height; `step` hears every frame (to repaint a line)."""

    def __init__(self, body: QWidget, step: Callable[[], None] = lambda: None):
        super().__init__(body)
        self._body = body
        self._step_hook = step
        self.open = not body.isHidden()
        self._from = 0
        self._to = 0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(FOLD_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._step)
        self._animation.finished.connect(self._done)

    def set_open(self, open_: bool, animate: bool = True) -> None:
        if open_ == self.open and self._animation.state() != QVariantAnimation.State.Running:
            return
        self.open = open_
        self._animation.stop()
        body = self._body
        if not animate or not body.window().isVisible():
            self._done()
            return
        self._from = body.height() if body.isVisible() else 0
        body.setMaximumHeight(self._from)
        body.setVisible(True)
        self._to = self._natural_height() if open_ else 0
        self._animation.start()

    def finish(self) -> None:
        if self._animation.state() == QVariantAnimation.State.Running:
            self._animation.stop()
            self._done()

    def _natural_height(self) -> int:
        body = self._body
        width = body.width() or (body.parentWidget().width() if body.parentWidget() is not None else 0)
        if body.hasHeightForWidth() and width > 0:
            return max(0, body.heightForWidth(width))
        return max(0, body.sizeHint().height())

    def _step(self, value: Any) -> None:
        progress = cubic_bezier(EASING, float(value))
        self._body.setMaximumHeight(round(self._from + (self._to - self._from) * progress))
        lay_out_above(self._body)
        self._step_hook()

    def _done(self) -> None:
        self._body.setMaximumHeight(UNBOUNDED)
        self._body.setVisible(self.open)
        self._step_hook()
