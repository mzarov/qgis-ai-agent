import re
from typing import Any

from qgis.PyQt.QtGui import QColor

# Qt reads eight hex digits as #AARRGGBB; CSS, and the people writing colours, mean #RRGGBBAA.
HEX_WITH_ALPHA = re.compile(r"#[0-9a-fA-F]{8}")


def parse_color(value: Any, label: str = "Colour") -> QColor:
    text = str(value or "").strip()
    if HEX_WITH_ALPHA.fullmatch(text):
        color = QColor(text[:7])
        color.setAlpha(int(text[7:], 16))
    else:
        color = QColor(text)
    if not color.isValid():
        raise ValueError(
            f"{label} '{value}' was not recognised. Use a hex value such as #1f78b4 "
            "or an English colour name such as steelblue."
        )
    return color
