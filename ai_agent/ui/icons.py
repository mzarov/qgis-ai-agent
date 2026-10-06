"""The interface icons: Lucide outlines (ISC licence) in `ui/glyphs`, tinted to the caller's colour.

One family, one stroke weight (1.75 on a 24 grid), recoloured per theme. A
null QIcon means the artwork could not be drawn; callers then show a glyph.
"""

import os
from typing import Any

from qgis.PyQt.QtGui import QIcon

from ai_agent.ui import svg_art

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glyphs")
NAMES = {
    "sessions": "history",
    "clear": "square-pen",
    "settings": "settings",
    "connection": "plug",
    "privacy": "shield-check",
    "skills": "book-open",
    "geocoding": "map-pin",
    "advanced": "sliders-horizontal",
    "layer": "layers",
    "collapsed": "chevron-right",
    "expanded": "chevron-down",
    "rename": "pencil",
    "delete": "trash-2",
    "rewind": "undo-2",
}


def glyph(role: str, colour: Any, size: int) -> QIcon:
    image = svg_art.tinted(os.path.join(FOLDER, f"{NAMES[role]}.svg"), colour, size)
    return QIcon() if image is None else QIcon(image)


def drawn(role: str, colour: Any, size: int) -> QIcon | None:
    """The glyph, or None when it cannot be drawn and the caller shows its text fallback."""
    try:
        icon = glyph(role, colour, size)
    except Exception:
        return None
    return None if icon.isNull() else icon


def chevron(expanded: bool, colour: Any, size: int) -> QIcon:
    return glyph("expanded" if expanded else "collapsed", colour, size)
