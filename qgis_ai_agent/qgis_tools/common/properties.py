from dataclasses import dataclass
from typing import Any, Callable

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.common.values import suggest_fields
from qgis_ai_agent.qgis_tools.common.colors import parse_color

KIND_TEXT = "text"
KIND_NUMBER = "number"
KIND_BOOLEAN = "boolean"
KIND_COLOR = "color"
KIND_ENUM = "enum"
FALSE_WORDS = ("false", "0", "no", "off")


@dataclass(frozen=True)
class StyleProperty:
    name: str
    kind: str
    description: str
    target: str
    apply: Callable[[Any, Any], None]
    options: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""

    def describe(self) -> dict[str, Any]:
        described: dict[str, Any] = {
            "name": self.name,
            "type": self.kind,
            "description": self.description,
        }
        if self.options:
            described["options"] = list(self.options)
        if self.minimum is not None:
            described["min"] = self.minimum
        if self.maximum is not None:
            described["max"] = self.maximum
        if self.unit:
            described["unit"] = self.unit
        return described


class PropertySet:
    def __init__(self, subject: str, properties: list[StyleProperty]):
        self.subject = subject
        self.properties = list(properties)
        self.by_name = {item.name: item for item in properties}

    def names(self) -> list[str]:
        return [item.name for item in self.properties]

    def catalogue(self) -> list[dict[str, Any]]:
        return [item.describe() for item in self.properties]

    def check_known(self, properties: dict[str, Any]) -> None:
        unknown = [key for key in properties if key not in self.by_name]
        if not unknown:
            return
        listed = ", ".join(f"'{key}'" for key in unknown)
        raise ValueError(
            f"Unknown properties ({self.subject}): {listed}. "
            f"{suggest_fields(unknown, self.names())}"
        )

    def coerce_all(self, properties: dict[str, Any]) -> dict[str, Any]:
        self.check_known(properties)
        return {key: self.coerce(key, value) for key, value in properties.items()}

    def coerce(self, key: str, value: Any) -> Any:
        prop = self.by_name[key]
        if prop.kind == KIND_BOOLEAN:
            return as_bool(value)
        if prop.kind == KIND_COLOR:
            return as_color(prop, value)
        if prop.kind == KIND_ENUM:
            return as_option(prop, value)
        if prop.kind == KIND_NUMBER:
            return as_number(prop, value)
        return str(value or "").strip()

    def targeted(self, properties: dict[str, Any], target: str) -> list[tuple[StyleProperty, Any]]:
        return [
            (self.by_name[key], value)
            for key, value in properties.items()
            if self.by_name[key].target == target
        ]

    def mentions(self, properties: dict[str, Any], target: str) -> bool:
        return any(self.by_name[key].target == target for key in properties)


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in FALSE_WORDS
    return bool(value)


def as_color(prop: StyleProperty, value: Any) -> str:
    text = str(value or "").strip()
    parse_color(text, f"Property '{prop.name}'")
    return text


def as_option(prop: StyleProperty, value: Any) -> str:
    name = str(value or "").strip().lower()
    if name not in prop.options:
        raise ValueError(
            f"Property '{prop.name}' has no value '{value}'. "
            f"Available: {', '.join(prop.options)}."
        )
    return name


def as_number(prop: StyleProperty, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Property '{prop.name}' takes a number, got '{value}'.")
    below = prop.minimum is not None and number < prop.minimum
    above = prop.maximum is not None and number > prop.maximum
    if below or above:
        unit = f" {prop.unit}" if prop.unit else ""
        raise ValueError(
            f"Property '{prop.name}' must be between {prop.minimum:g} "
            f"and {prop.maximum:g}{unit}, got {number:g}."
        )
    return number


def setter(attribute: str) -> Callable[[Any, Any], None]:
    def apply(target: Any, value: Any) -> None:
        setattr(target, attribute, value)

    return apply


def method(*names: str) -> Callable[[Any, Any], None]:
    def apply(target: Any, value: Any) -> None:
        for name in names:
            found = getattr(target, name, None)
            if found is not None:
                found(value)
                return
        raise AttributeError(names[0])

    return apply


def ignored() -> Callable[[Any, Any], None]:
    def apply(target: Any, value: Any) -> None:
        return None

    return apply


SHOWN_IN_SUMMARY = 4


def properties_of(params: dict[str, Any], subject: str) -> dict[str, Any]:
    properties = params.get("properties")
    if properties is None:
        return {}
    if not isinstance(properties, dict):
        raise ValueError(
            f"Properties ({subject}) are passed as an object of key-value pairs, "
            "not as a string or a list. Call describe_style_options for the list of keys."
        )
    return dict(properties)


def shown(properties: dict[str, Any], known: PropertySet) -> str:
    pairs = [f"{key}={value}" for key, value in properties.items() if key in known.by_name]
    if not pairs:
        return tr("defaults")
    if len(pairs) <= SHOWN_IN_SUMMARY:
        return ", ".join(pairs)
    head = ", ".join(pairs[:SHOWN_IN_SUMMARY])
    return tr("{0} and {1} more").format(head, len(pairs) - SHOWN_IN_SUMMARY)
