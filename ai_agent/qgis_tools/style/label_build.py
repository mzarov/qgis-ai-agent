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
    TARGET_BACKGROUND,
    TARGET_BUFFER,
    TARGET_FONT,
    TARGET_FORMAT,
    TARGET_SETTINGS,
    TARGET_SHADOW,
)

MILLIMETRES = Qgis.RenderUnit.Millimeters
SIMPLE_LABELING = "simple"
OFFSET_KEYS = frozenset({"offset_x", "offset_y"})
DISTANCE_KEYS = frozenset({"distance"})
SUB_SETTINGS = (
    (TARGET_BUFFER, "buffer", "setBuffer"),
    (TARGET_SHADOW, "shadow", "setShadow"),
    (TARGET_BACKGROUND, "background", "setBackground"),
)


def build_settings(properties: dict[str, Any], base: Any = None) -> QgsPalLayerSettings:
    """Fresh label settings, or `base` (the layer's current ones) changed only where given."""
    if base is None:
        settings = QgsPalLayerSettings()
        settings.isExpression = False
        settings.offsetUnits = MILLIMETRES
        settings.distUnits = MILLIMETRES
    else:
        settings = base
        if "field" in properties:
            settings.isExpression = False
        # Catalogue offsets and distances are millimetres; untouched ones keep
        # whatever unit the user chose.
        if OFFSET_KEYS & properties.keys():
            settings.offsetUnits = MILLIMETRES
        if DISTANCE_KEYS & properties.keys():
            settings.distUnits = MILLIMETRES
    _apply_group(settings, properties, TARGET_SETTINGS)
    settings.setFormat(build_format(properties, settings.format() if base is not None else None))
    return settings


def build_format(properties: dict[str, Any], base: Any = None) -> QgsTextFormat:
    text_format = base if base is not None else QgsTextFormat()
    font = text_format.font()
    _apply_group(font, properties, TARGET_FONT)
    text_format.setFont(font)
    _apply_group(text_format, properties, TARGET_FORMAT)
    for target, getter, setter_name in SUB_SETTINGS:
        if base is not None and not addresses(properties, target):
            continue
        subject = getattr(text_format, getter)() if base is not None else _fresh_sub(target)
        getattr(text_format, setter_name)(_sub(subject, properties, target))
    return text_format


def _fresh_sub(target: str) -> Any:
    if target == TARGET_BUFFER:
        return QgsTextBufferSettings()
    if target == TARGET_SHADOW:
        return QgsTextShadowSettings()
    return QgsTextBackgroundSettings()


def current_simple_settings(layer: Any) -> Any:
    """The layer's live simple label settings (a copy), or None when labels are off or rule-based."""
    try:
        if not layer.labelsEnabled():
            return None
        labeling = layer.labeling()
        if labeling is None or labeling.type() != SIMPLE_LABELING:
            return None
        return labeling.settings()
    except Exception:
        return None


def addresses(properties: dict[str, Any], target: str) -> bool:
    return SWITCHES.get(target, "") in properties or LABELS.mentions(properties, target)


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
