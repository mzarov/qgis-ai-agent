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
POINTS = Qgis.RenderUnit.Points
INCHES = Qgis.RenderUnit.Inches
SIMPLE_LABELING = "simple"
OFFSET_KEYS = frozenset({"offset_x", "offset_y"})
OTHER_OFFSET = {"offset_x": ("yOffset", "offset_y"), "offset_y": ("xOffset", "offset_x")}
# A lone offset keeps a paper unit by conversion; one unit holds both offsets, so it cannot follow map units.
MM_TO_PAPER = {POINTS: 72.0 / 25.4, INCHES: 1.0 / 25.4}
# Around a point QGIS ignores offsets: they move a label placed over it.
OFFSET_GEOMETRIES = frozenset({"point", "polygon"})
OFFSET_UNITS_CONFLICT = (
    "The labels of this layer keep their offsets in {unit} and {other} is {value}: one unit holds both, so "
    "give offset_x and offset_y together, in millimetres, or the other offset is read in the wrong unit."
)
DISTANCE_KEYS = frozenset({"distance"})
SUB_SETTINGS = (
    (TARGET_BUFFER, "buffer", "setBuffer"),
    (TARGET_SHADOW, "shadow", "setShadow"),
    (TARGET_BACKGROUND, "background", "setBackground"),
)


def build_settings(properties: dict[str, Any], base: Any = None, geometry: str = "") -> QgsPalLayerSettings:
    if base is None:
        settings = QgsPalLayerSettings()
        settings.isExpression = False
        settings.offsetUnits = MILLIMETRES
        settings.distUnits = MILLIMETRES
    else:
        settings = base
        if "field" in properties:
            settings.isExpression = False
        # Catalogue offsets and distances are millimetres; untouched ones keep the user's unit.
        properties = _offsets_in_base_unit(settings, properties)
        if DISTANCE_KEYS & properties.keys():
            settings.distUnits = MILLIMETRES
    _apply_group(settings, properties, TARGET_SETTINGS)
    if _offsets_ignored(settings, properties, geometry):
        settings.placement = Qgis.LabelPlacement.OverPoint
    settings.setFormat(build_format(properties, settings.format() if base is not None else None))
    return settings


def _offsets_ignored(settings: Any, properties: dict[str, Any], geometry: str) -> bool:
    if not OFFSET_KEYS & properties.keys() or "placement" in properties or geometry not in OFFSET_GEOMETRIES:
        return False
    return bool(settings.placement == Qgis.LabelPlacement.AroundPoint)


def offset_conflict(base: Any, properties: dict[str, Any]) -> str:
    given = OFFSET_KEYS & properties.keys()
    if base is None or len(given) != 1 or base.offsetUnits == MILLIMETRES or base.offsetUnits in MM_TO_PAPER:
        return ""
    attribute, other = OTHER_OFFSET[next(iter(given))]
    value = getattr(base, attribute, 0.0)
    if not value:
        return ""
    unit = getattr(base.offsetUnits, "name", str(base.offsetUnits))
    return OFFSET_UNITS_CONFLICT.format(unit=unit, other=other, value=value)


def _offsets_in_base_unit(settings: Any, properties: dict[str, Any]) -> dict[str, Any]:
    given = OFFSET_KEYS & properties.keys()
    if not given:
        return properties
    factor = MM_TO_PAPER.get(settings.offsetUnits) if len(given) == 1 else None
    if factor is not None:
        return {**properties, **{key: float(properties[key]) * factor for key in given}}
    conflict = offset_conflict(settings, properties)
    if conflict:
        raise ValueError(conflict)
    settings.offsetUnits = MILLIMETRES
    return properties


def build_format(properties: dict[str, Any], base: Any = None) -> QgsTextFormat:
    text_format = base if base is not None else QgsTextFormat()
    font = text_format.font()
    _apply_group(font, properties, TARGET_FONT)
    text_format.setFont(font)
    _apply_group(text_format, properties, TARGET_FORMAT)
    # Catalogue sizes are points; an untouched size keeps the user's unit.
    if "size" in properties:
        text_format.setSizeUnit(POINTS)
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
        if target == TARGET_BUFFER and "buffer_size" in properties:
            subject.setSizeUnit(MILLIMETRES)
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
