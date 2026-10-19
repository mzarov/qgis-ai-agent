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
    name = FILES.get(title)
    return None if name is None else svg_art.tinted(os.path.join(FOLDER, f"{name}.svg"), colour, size)
