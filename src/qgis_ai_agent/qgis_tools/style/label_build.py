from typing import Any

from qgis.core import (
    Qgis,
    QgsPalLayerSettings,
    QgsTextBackgroundSettings,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsTextShadowSettings,
)

from qgis_ai_agent.qgis_tools.common.values import suggest_fields
from qgis_ai_agent.qgis_tools.style.apply import parse_color
from qgis_ai_agent.qgis_tools.style.label_catalogue import (
    BY_NAME,
    GROUP_TARGETS,
    PLACEMENTS,
    SWITCHES,
    TARGET_FONT,
    TARGET_FORMAT,
    TARGET_SETTINGS,
    LabelProperty,
    names,
)

FALSE_WORDS = ("false", "0", "no", "off", "нет")
MILLIMETRES = Qgis.RenderUnit.Millimeters


def check_known(properties: dict[str, Any]) -> None:
    unknown = [key for key in properties if key not in BY_NAME]
    if unknown:
        listed = ", ".join(f"«{key}»" for key in unknown)
        raise ValueError(f"Неизвестные свойства подписи: {listed}. {suggest_fields(unknown, names())}")


def coerce_all(properties: dict[str, Any]) -> dict[str, Any]:
    check_known(properties)
    return {key: coerce(BY_NAME[key], value) for key, value in properties.items()}


def coerce(prop: LabelProperty, value: Any) -> Any:
    if prop.kind == "boolean":
        return as_bool(value)
    if prop.kind == "color":
        return str(value or "").strip()
    if prop.kind == "enum":
        return as_option(prop, value)
    if prop.kind == "number":
        return as_number(prop, value)
    return str(value or "").strip()


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in FALSE_WORDS
    return bool(value)


def as_option(prop: LabelProperty, value: Any) -> str:
    name = str(value or "").strip().lower()
    if name not in prop.options:
        raise ValueError(
            f"У свойства «{prop.name}» нет значения «{value}». "
            f"Доступны: {', '.join(prop.options)}."
        )
    return name


def as_number(prop: LabelProperty, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Свойство «{prop.name}» задаётся числом, получено «{value}».")
    below = prop.minimum is not None and number < prop.minimum
    above = prop.maximum is not None and number > prop.maximum
    if below or above:
        unit = f" {prop.unit}" if prop.unit else ""
        raise ValueError(
            f"Свойство «{prop.name}» должно быть от {prop.minimum:g} до {prop.maximum:g}{unit}."
        )
    return number


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
    return any(BY_NAME[key].target == target for key in properties)


def _sub(subject: Any, properties: dict[str, Any], target: str) -> Any:
    enabled = wants(properties, target)
    subject.setEnabled(enabled)
    if enabled:
        _apply_group(subject, properties, target)
    return subject


def _apply_group(subject: Any, properties: dict[str, Any], target: str) -> None:
    for key, value in properties.items():
        prop = BY_NAME[key]
        if prop.target != target or (target in GROUP_TARGETS and key in SWITCHES.values()):
            continue
        if key == "enabled":
            continue
        prop.apply(subject, _native(prop, value))


def _native(prop: LabelProperty, value: Any) -> Any:
    if prop.kind == "color":
        return parse_color(value, f"Свойство «{prop.name}»")
    if prop.kind == "enum" and prop.name == "placement":
        return getattr(Qgis.LabelPlacement, PLACEMENTS[value])
    return value
