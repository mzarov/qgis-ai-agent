import os
from typing import Any

from qgis.PyQt.QtGui import QIcon

from ai_agent.ui import svg_art

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glyphs")
NAMES = {
    "float": "picture-in-picture-2",
    "close": "x",
    "new": "plus",
    "settings": "sliders-horizontal",
    "send": "arrow-up",
    "mode": "shield",
    "saved": "clock",
    "file": "file",
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
    "connectors": "globe",
    "personalisation": "user",
    "rewind": "undo-2",
    "unplugged": "unplug",
    "key": "key-round",
    "busy": "hourglass",
    "late": "clock",
    "alert": "circle-alert",
    "inspect": "layers",
    "project": "layers",
    "style": "palette",
    "processing": "square-play",
    "osm": "map",
    "data": "database",
    "draw": "pen-tool",
    "edit": "pencil",
    "fields": "columns-3",
    "layout": "printer",
    "python": "code",
    "web": "globe",
    "annotations": "sticky-note",
    "three_d": "box",
    "tables": "table",
    "sql": "database",
    "charts": "chart-column",
    "plugins": "puzzle",
    "quality": "shield-check",
    "knowledge": "book-open",
    "check": "check",
    "image": "image",
    "point": "map-pin",
    "area": "square-dashed",
    "measure": "square-dashed",
    "search": "search",
}


def glyph(role: str, colour: Any, size: int) -> QIcon:
    image = svg_art.tinted(os.path.join(FOLDER, f"{NAMES[role]}.svg"), colour, size)
    return QIcon() if image is None else QIcon(image)


def drawn(role: str, colour: Any, size: int) -> QIcon | None:
    try:
        icon = glyph(role, colour, size)
    except Exception:
        return None
    return None if icon.isNull() else icon


def chevron(expanded: bool, colour: Any, size: int) -> QIcon:
    return glyph("expanded" if expanded else "collapsed", colour, size)
