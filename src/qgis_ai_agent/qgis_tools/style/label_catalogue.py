from qgis_ai_agent.qgis_tools.style.properties import (
    KIND_BOOLEAN,
    KIND_COLOR,
    KIND_ENUM,
    KIND_NUMBER,
    KIND_TEXT,
    PropertySet,
    StyleProperty,
    ignored,
    method,
    setter,
)

SUBJECT = "подписи"
TARGET_SETTINGS = "settings"
TARGET_FORMAT = "format"
TARGET_FONT = "font"
TARGET_BUFFER = "buffer"
TARGET_SHADOW = "shadow"
TARGET_BACKGROUND = "background"

GROUP_TARGETS = (TARGET_BUFFER, TARGET_SHADOW, TARGET_BACKGROUND)
SWITCHES = {TARGET_BUFFER: "buffer", TARGET_SHADOW: "shadow", TARGET_BACKGROUND: "background"}

PLACEMENTS = {
    "over": "OverPoint",
    "around": "AroundPoint",
    "horizontal": "Horizontal",
    "curved": "Curved",
    "line": "Line",
    "free": "Free",
    "outside": "OutsidePolygons",
}

LABELS = PropertySet(
    SUBJECT,
    [
        StyleProperty("field", KIND_TEXT, "Поле, значениями которого подписывать объекты", TARGET_SETTINGS, setter("fieldName")),
        StyleProperty("enabled", KIND_BOOLEAN, "false — выключить подписи слоя целиком", TARGET_SETTINGS, ignored()),
        StyleProperty("font", KIND_TEXT, "Семейство шрифта, например Arial или Times New Roman", TARGET_FONT, method("setFamily")),
        StyleProperty("bold", KIND_BOOLEAN, "Полужирное начертание", TARGET_FONT, method("setBold")),
        StyleProperty("italic", KIND_BOOLEAN, "Курсив", TARGET_FONT, method("setItalic")),
        StyleProperty("size", KIND_NUMBER, "Размер шрифта", TARGET_FORMAT, method("setSize"), minimum=3.0, maximum=72.0, unit="пункты"),
        StyleProperty("color", KIND_COLOR, "Цвет самого текста", TARGET_FORMAT, method("setColor")),
        StyleProperty("opacity", KIND_NUMBER, "Прозрачность подписи: 1 — непрозрачная", TARGET_FORMAT, method("setOpacity"), minimum=0.0, maximum=1.0),
        StyleProperty("buffer", KIND_BOOLEAN, "Обводка вокруг текста (ореол): false — убрать", TARGET_BUFFER, ignored()),
        StyleProperty("buffer_color", KIND_COLOR, "Цвет обводки текста, обычно white", TARGET_BUFFER, method("setColor")),
        StyleProperty("buffer_size", KIND_NUMBER, "Толщина обводки текста", TARGET_BUFFER, method("setSize"), minimum=0.1, maximum=10.0, unit="мм"),
        StyleProperty("offset_x", KIND_NUMBER, "Сдвиг подписи вправо от точки привязки", TARGET_SETTINGS, setter("xOffset"), minimum=-100.0, maximum=100.0, unit="мм"),
        StyleProperty("offset_y", KIND_NUMBER, "Сдвиг подписи вниз от точки привязки; вверх — отрицательное число", TARGET_SETTINGS, setter("yOffset"), minimum=-100.0, maximum=100.0, unit="мм"),
        StyleProperty("distance", KIND_NUMBER, "Отступ подписи от самой геометрии", TARGET_SETTINGS, setter("dist"), minimum=0.0, maximum=100.0, unit="мм"),
        StyleProperty("rotation", KIND_NUMBER, "Поворот подписи", TARGET_SETTINGS, setter("angleOffset"), minimum=-360.0, maximum=360.0, unit="градусы"),
        StyleProperty(
            "placement",
            KIND_ENUM,
            "Как подпись ставится относительно объекта: over — по центру, around — "
            "вокруг точки, horizontal — горизонтально, curved — по кривой линии, "
            "line — вдоль линии, outside — снаружи полигона",
            TARGET_SETTINGS,
            setter("placement"),
            options=tuple(sorted(PLACEMENTS)),
        ),
        StyleProperty("shadow", KIND_BOOLEAN, "Тень под подписью: false — убрать", TARGET_SHADOW, ignored()),
        StyleProperty("shadow_color", KIND_COLOR, "Цвет тени под подписью", TARGET_SHADOW, method("setColor")),
        StyleProperty("background", KIND_BOOLEAN, "Подложка под подписью: false — убрать", TARGET_BACKGROUND, ignored()),
        StyleProperty("background_color", KIND_COLOR, "Цвет подложки под подписью", TARGET_BACKGROUND, method("setFillColor")),
    ],
)
