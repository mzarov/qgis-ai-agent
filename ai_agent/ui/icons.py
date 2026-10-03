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
}


def glyph(role: str, colour: Any, size: int) -> QIcon:
    image = svg_art.tinted(os.path.join(FOLDER, f"{NAMES[role]}.svg"), colour, size)
    return QIcon() if image is None else QIcon(image)


def sessions(colour: Any, size: int) -> QIcon:
    return glyph("sessions", colour, size)


def clear(colour: Any, size: int) -> QIcon:
    return glyph("clear", colour, size)


def settings(colour: Any, size: int) -> QIcon:
    return glyph("settings", colour, size)


def connection(colour: Any, size: int) -> QIcon:
    return glyph("connection", colour, size)


def privacy(colour: Any, size: int) -> QIcon:
    return glyph("privacy", colour, size)


def skills(colour: Any, size: int) -> QIcon:
    return glyph("skills", colour, size)


def geocoding(colour: Any, size: int) -> QIcon:
    return glyph("geocoding", colour, size)


def advanced(colour: Any, size: int) -> QIcon:
    return glyph("advanced", colour, size)


def layer(colour: Any, size: int) -> QIcon:
    return glyph("layer", colour, size)


def chevron(expanded: bool, colour: Any, size: int) -> QIcon:
    return glyph("expanded" if expanded else "collapsed", colour, size)
