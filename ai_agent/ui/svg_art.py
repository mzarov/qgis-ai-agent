"""Render a monochrome SVG at a logical size and recolour it, so artwork follows the theme."""

from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QGuiApplication, QPainter, QPixmap

MAX_RATIO = 4.0


def tinted(path: str, colour: Any, size: int) -> QPixmap | None:
    """The SVG at `path` drawn `size` logical pixels square in `colour`; None when it cannot be drawn."""
    try:
        from qgis.PyQt.QtSvg import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    ratio = _ratio()
    image = QPixmap(int(size * ratio), int(size * ratio))
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        # Keep the artwork's shape, replace its ink: the source files are plain black.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(QRectF(0, 0, size, size), colour)
    finally:
        painter.end()
    return image


def _ratio() -> float:
    try:
        found = float(QGuiApplication.primaryScreen().devicePixelRatio())
    except Exception:
        return 1.0
    return found if 1.0 <= found <= MAX_RATIO else 1.0
