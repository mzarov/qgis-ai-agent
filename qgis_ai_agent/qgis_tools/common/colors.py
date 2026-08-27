from typing import Any

from qgis.PyQt.QtGui import QColor


def parse_color(value: Any, label: str = "Цвет") -> QColor:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        raise ValueError(
            f"{label} «{value}» не распознан. Используйте hex вида #1f78b4 "
            "или английское имя цвета вида steelblue."
        )
    return color
