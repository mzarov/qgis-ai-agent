from typing import Any

from qgis.core import (
    Qgis,
    QgsPalLayerSettings,
    QgsTextBackgroundSettings,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsTextShadowSettings,
)

from ai_agent.qgis_tools.common.colors import parse_color
from ai_agent.qgis_tools.common.properties import KIND_COLOR, KIND_ENUM, StyleProperty
from ai_agent.qgis_tools.style.label_catalogue import (
    LABELS,
    PLACEMENTS,
    SWITCHES,
    TARGET_FONT,
    TARGET_FORMAT,
    TARGET_SETTINGS,
)

MILLIMETRES = Qgis.RenderUnit.Millimeters


def build_settings(properties: dict[str, Any]) -> QgsPalLayerSettings:
    settings = QgsPalLayerSettings()
    settings.isExpression = False
    settings.offsetUnits = MILLIMETRES
    settings.distUnits = MILLIMETRES
    _apply_group(settings, properties, TARGET_SETTINGS)
    settings.setFormat(build_format(properties))
    return settings


def build_format(properties: dict[str, Any]) -> QgsTextFormat:
    text_format = QgsTextFormat()
    font = text_format.font()
    _apply_group(font, properties, TARGET_FONT)
    text_format.setFont(font)
    _apply_group(text_format, properties, TARGET_FORMAT)
    text_format.setBuffer(_sub(QgsTextBufferSettings(), properties, "buffer"))
    text_format.setShadow(_sub(QgsTextShadowSettings(), properties, "shadow"))
    text_format.setBackground(_sub(QgsTextBackgroundSettings(), properties, "background"))
    return text_format


def wants(properties: dict[str, Any], target: str) -> bool:
    switch = SWITCHES.get(target, "")
    if switch in properties:
        return bool(properties[switch])
    return LABELS.mentions(properties, target)


def _sub(subject: Any, properties: dict[str, Any], target: str) -> Any:
    enabled = wants(properties, target)
    subject.setEnabled(enabled)
    if enabled:
        _apply_group(subject, properties, target)
    return subject


def _apply_group(subject: Any, properties: dict[str, Any], target: str) -> None:
    for prop, value in LABELS.targeted(properties, target):
        prop.apply(subject, _native(prop, value))


def _native(prop: StyleProperty, value: Any) -> Any:
    if prop.kind == KIND_COLOR:
        return parse_color(value, f"Property '{prop.name}'")
    if prop.kind == KIND_ENUM and prop.name == "placement":
        return getattr(Qgis.LabelPlacement, PLACEMENTS[value])
    return value
