from qgis_ai_agent.qgis_tools.common.properties import (
    KIND_COLOR,
    KIND_ENUM,
    KIND_NUMBER,
    PropertySet,
    StyleProperty,
    method,
)

SUBJECT = "символ слоя"
TARGET_SYMBOL = "symbol"
TARGET_LAYER = "layer"

SHAPES = {
    "circle": "Circle",
    "square": "Square",
    "triangle": "Triangle",
    "diamond": "Diamond",
    "star": "Star",
    "cross": "Cross",
    "pentagon": "Pentagon",
    "hexagon": "Hexagon",
}
PEN_STYLES = {
    "solid": "SolidLine",
    "dash": "DashLine",
    "dot": "DotLine",
    "dashdot": "DashDotLine",
    "none": "NoPen",
}
BRUSH_STYLES = {
    "solid": "SolidPattern",
    "none": "NoBrush",
    "horizontal": "HorPattern",
    "vertical": "VerPattern",
    "diagonal": "BDiagPattern",
    "cross": "CrossPattern",
    "dense": "Dense4Pattern",
}

SYMBOLS = PropertySet(
    SUBJECT,
    [
        StyleProperty(
            "color",
            KIND_COLOR,
            "Основной цвет: заливка полигона, цвет линии или точки",
            TARGET_SYMBOL,
            method("setColor"),
        ),
        StyleProperty(
            "opacity",
            KIND_NUMBER,
            "Прозрачность символа: 1 — непрозрачный",
            TARGET_SYMBOL,
            method("setOpacity"),
            minimum=0.0,
            maximum=1.0,
        ),
        StyleProperty(
            "size",
            KIND_NUMBER,
            "Размер точки или толщина линии; для полигонов не применяется",
            TARGET_SYMBOL,
            method("setSize", "setWidth"),
            minimum=0.05,
            maximum=100.0,
            unit="мм",
        ),
        StyleProperty(
            "stroke_color",
            KIND_COLOR,
            "Цвет обводки вокруг точки или полигона",
            TARGET_LAYER,
            method("setStrokeColor"),
        ),
        StyleProperty(
            "stroke_width",
            KIND_NUMBER,
            "Толщина обводки вокруг точки или полигона",
            TARGET_LAYER,
            method("setStrokeWidth"),
            minimum=0.0,
            maximum=20.0,
            unit="мм",
        ),
        StyleProperty(
            "stroke_style",
            KIND_ENUM,
            "Штрих линии или обводки: solid — сплошная, dash — пунктир, dot — "
            "точками, dashdot — штрихпунктир, none — без обводки",
            TARGET_LAYER,
            method("setStrokeStyle", "setPenStyle"),
            options=tuple(sorted(PEN_STYLES)),
        ),
        StyleProperty(
            "shape",
            KIND_ENUM,
            "Форма значка для точечных слоёв: circle, square, triangle, diamond, "
            "star, cross, pentagon, hexagon",
            TARGET_LAYER,
            method("setShape"),
            options=tuple(sorted(SHAPES)),
        ),
        StyleProperty(
            "fill_style",
            KIND_ENUM,
            "Штриховка заливки полигона: solid — сплошная, none — без заливки, "
            "horizontal, vertical, diagonal, cross, dense",
            TARGET_LAYER,
            method("setBrushStyle"),
            options=tuple(sorted(BRUSH_STYLES)),
        ),
        StyleProperty(
            "angle",
            KIND_NUMBER,
            "Поворот значка для точечных слоёв",
            TARGET_LAYER,
            method("setAngle"),
            minimum=-360.0,
            maximum=360.0,
            unit="градусы",
        ),
    ],
)
