"""Provider logos: monochrome SVGs from Simple Icons (CC0), tinted with the theme's text colour.

Tinting keeps six brands reading as one set in both themes instead of six
competing colours. QtSvg ships with QGIS; where it is missing, callers fall
back to a monogram.
"""

import os
from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QGuiApplication, QPainter, QPixmap

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")
MAX_RATIO = 4.0
FILES = {
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Google Gemini": "googlegemini",
    "OpenRouter": "openrouter",
    "Ollama": "ollama",
    "LM Studio": "lmstudio",
}


def has_logo(title: str) -> bool:
    return title in FILES


def pixmap(title: str, colour: Any, size: int) -> QPixmap | None:
    """The provider's logo at `size` logical pixels in `colour`, or None when it cannot be drawn."""
    name = FILES.get(title)
    if name is None:
        return None
    try:
        from qgis.PyQt.QtSvg import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(os.path.join(FOLDER, f"{name}.svg"))
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
        # Keep the logo's shape, replace its ink: the source files are plain black.
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
