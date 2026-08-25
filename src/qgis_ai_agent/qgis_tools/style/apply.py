from typing import Any

from qgis.core import QgsStyle, QgsSymbol, QgsVectorLayer
from qgis.PyQt.QtGui import QColor

from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name
from qgis_ai_agent.qgis_tools.common.values import suggest_fields

RAMPS_SHOWN = 24
MIN_OPACITY = 0.0
MAX_OPACITY = 1.0


def require_vector_layer(layer_name: str) -> QgsVectorLayer:
    layer = find_layer_by_name(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(
            f"Слой «{layer_name}» не векторный. Оформление символами задаётся "
            "только для векторных слоёв."
        )
    return layer


def require_field(layer: QgsVectorLayer, field_name: str) -> str:
    names = field_names(layer)
    if field_name in names:
        return field_name
    raise ValueError(f"В слое «{layer.name()}» нет поля «{field_name}». {suggest_fields([field_name], names)}")


def field_names(layer: QgsVectorLayer) -> list[str]:
    try:
        return [field.name() for field in layer.fields()]
    except Exception:
        return []


def parse_color(value: Any, label: str = "Цвет") -> QColor:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        raise ValueError(
            f"{label} «{value}» не распознан. Используйте hex вида #1f78b4 "
            "или английское имя цвета вида steelblue."
        )
    return color


def resolve_ramp(name: str, fallbacks: tuple[str, ...] = ()):
    style = QgsStyle.defaultStyle()
    available = sorted(style.colorRampNames())
    wanted = (name or "").strip()
    if wanted:
        if wanted in available:
            return style.colorRamp(wanted)
        raise ValueError(f"Палитры «{wanted}» нет в QGIS. {describe_ramps(available)}")
    for candidate in fallbacks:
        if candidate in available:
            return style.colorRamp(candidate)
    if available:
        return style.colorRamp(available[0])
    raise ValueError(
        "В библиотеке QGIS нет ни одной палитры — задайте цвета списком через colors."
    )


def describe_ramps(available: list[str]) -> str:
    if not available:
        return "Библиотека палитр пуста — задайте цвета списком вместо палитры."
    shown = ", ".join(available[:RAMPS_SHOWN])
    if len(available) > RAMPS_SHOWN:
        return f"Доступные палитры (первые {RAMPS_SHOWN} из {len(available)}): {shown}."
    return f"Доступные палитры: {shown}."


def base_symbol(layer: QgsVectorLayer) -> QgsSymbol:
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    if symbol is None:
        raise ValueError(f"Не удалось создать символ для слоя «{layer.name()}».")
    return symbol


def coloured_symbol(layer: QgsVectorLayer, color: QColor) -> QgsSymbol:
    symbol = base_symbol(layer)
    symbol.setColor(color)
    return symbol


def clamp_opacity(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Прозрачность задаётся числом от 0 до 1, например 0.6.")
    return max(MIN_OPACITY, min(MAX_OPACITY, number))


def refresh(layer: QgsVectorLayer) -> None:
    try:
        layer.triggerRepaint()
    except Exception:
        pass
    try:
        from qgis.utils import iface

        iface.layerTreeView().refreshLayerSymbology(layer.id())
    except Exception:
        pass
