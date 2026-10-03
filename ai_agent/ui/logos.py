"""Provider logos: monochrome SVGs from Simple Icons (CC0), tinted with the theme's text colour.

Tinting keeps six brands reading as one set in both themes instead of six
competing colours. Where they cannot be drawn, callers fall back to a monogram.
"""

import os
from typing import Any

from qgis.PyQt.QtGui import QPixmap

from ai_agent.ui import svg_art

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")
FILES = {
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Google Gemini": "googlegemini",
    "OpenRouter": "openrouter",
    "Ollama": "ollama",
    "LM Studio": "lmstudio",
}


def pixmap(title: str, colour: Any, size: int) -> QPixmap | None:
    """The provider's logo at `size` logical pixels in `colour`, or None when it cannot be drawn."""
    name = FILES.get(title)
    return None if name is None else svg_art.tinted(os.path.join(FOLDER, f"{name}.svg"), colour, size)
