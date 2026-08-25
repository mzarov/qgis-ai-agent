from dataclasses import dataclass, field
from typing import Any, Callable

TARGET_SETTINGS = "settings"
TARGET_FORMAT = "format"
TARGET_FONT = "font"
TARGET_BUFFER = "buffer"
TARGET_SHADOW = "shadow"
TARGET_BACKGROUND = "background"

GROUP_TARGETS = (TARGET_BUFFER, TARGET_SHADOW, TARGET_BACKGROUND)

PLACEMENTS = {
    "over": "OverPoint",
    "around": "AroundPoint",
    "horizontal": "Horizontal",
    "curved": "Curved",
    "line": "Line",
    "free": "Free",
    "outside": "OutsidePolygons",
}


@dataclass(frozen=True)
class LabelProperty:
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


def _set(attribute: str) -> Callable[[Any, Any], None]:
    def apply(target: Any, value: Any) -> None:
        setattr(target, attribute, value)

    return apply


def _call(method: str) -> Callable[[Any, Any], None]:
    def apply(target: Any, value: Any) -> None:
        getattr(target, method)(value)

    return apply


PROPERTIES: list[LabelProperty] = [
    LabelProperty("field", "text", "Поле, значениями которого подписывать объекты", TARGET_SETTINGS, _set("fieldName")),
    LabelProperty("enabled", "boolean", "false — выключить подписи слоя целиком", TARGET_SETTINGS, lambda target, value: None),
    LabelProperty("font", "text", "Семейство шрифта, например Arial или Times New Roman", TARGET_FONT, _call("setFamily")),
    LabelProperty("bold", "boolean", "Полужирное начертание", TARGET_FONT, _call("setBold")),
    LabelProperty("italic", "boolean", "Курсив", TARGET_FONT, _call("setItalic")),
    LabelProperty("size", "number", "Размер шрифта", TARGET_FORMAT, _call("setSize"), minimum=3.0, maximum=72.0, unit="пункты"),
    LabelProperty("color", "color", "Цвет самого текста", TARGET_FORMAT, _call("setColor")),
    LabelProperty("opacity", "number", "Прозрачность подписи: 1 — непрозрачная", TARGET_FORMAT, _call("setOpacity"), minimum=0.0, maximum=1.0),
    LabelProperty("buffer", "boolean", "Обводка вокруг текста (ореол): false — убрать", TARGET_BUFFER, lambda target, value: None),
    LabelProperty("buffer_color", "color", "Цвет обводки текста, обычно white", TARGET_BUFFER, _call("setColor")),
    LabelProperty("buffer_size", "number", "Толщина обводки текста", TARGET_BUFFER, _call("setSize"), minimum=0.1, maximum=10.0, unit="мм"),
    LabelProperty("offset_x", "number", "Сдвиг подписи вправо от точки привязки", TARGET_SETTINGS, _set("xOffset"), minimum=-100.0, maximum=100.0, unit="мм"),
    LabelProperty("offset_y", "number", "Сдвиг подписи вниз от точки привязки", TARGET_SETTINGS, _set("yOffset"), minimum=-100.0, maximum=100.0, unit="мм"),
    LabelProperty("distance", "number", "Отступ подписи от самой геометрии", TARGET_SETTINGS, _set("dist"), minimum=0.0, maximum=100.0, unit="мм"),
    LabelProperty("rotation", "number", "Поворот подписи", TARGET_SETTINGS, _set("angleOffset"), minimum=-360.0, maximum=360.0, unit="градусы"),
    LabelProperty(
        "placement",
        "enum",
        "Как подпись ставится относительно объекта: over — по центру, around — "
        "вокруг точки, horizontal — горизонтально, curved — по кривой линии, "
        "line — вдоль линии, outside — снаружи полигона",
        TARGET_SETTINGS,
        _set("placement"),
        options=tuple(sorted(PLACEMENTS)),
    ),
    LabelProperty("shadow", "boolean", "Тень под подписью: false — убрать", TARGET_SHADOW, lambda target, value: None),
    LabelProperty("shadow_color", "color", "Цвет тени под подписью", TARGET_SHADOW, _call("setColor")),
    LabelProperty("background", "boolean", "Подложка под подписью: false — убрать", TARGET_BACKGROUND, lambda target, value: None),
    LabelProperty("background_color", "color", "Цвет подложки под подписью", TARGET_BACKGROUND, _call("setFillColor")),
]

BY_NAME: dict[str, LabelProperty] = {item.name: item for item in PROPERTIES}
SWITCHES: dict[str, str] = {
    TARGET_BUFFER: "buffer",
    TARGET_SHADOW: "shadow",
    TARGET_BACKGROUND: "background",
}


def names() -> list[str]:
    return [item.name for item in PROPERTIES]


def catalogue() -> list[dict[str, Any]]:
    return [item.describe() for item in PROPERTIES]
