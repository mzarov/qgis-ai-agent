from typing import Any

from qgis.PyQt.QtGui import QColor


def parse_color(value: Any, label: str = "Colour") -> QColor:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        raise ValueError(
            f"{label} '{value}' was not recognised. Use a hex value such as #1f78b4 "
            "or an English colour name such as steelblue."
        )
    return color
