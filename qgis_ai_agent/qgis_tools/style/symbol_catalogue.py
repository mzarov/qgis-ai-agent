from qgis_ai_agent.qgis_tools.common.properties import (
    KIND_COLOR,
    KIND_ENUM,
    KIND_NUMBER,
    PropertySet,
    StyleProperty,
    method,
)

SUBJECT = "layer symbol"
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
            "Main colour: polygon fill, line colour or point colour",
            TARGET_SYMBOL,
            method("setColor"),
        ),
        StyleProperty(
            "opacity",
            KIND_NUMBER,
            "Opacity of the symbol: 1 is fully opaque",
            TARGET_SYMBOL,
            method("setOpacity"),
            minimum=0.0,
            maximum=1.0,
        ),
        StyleProperty(
            "size",
            KIND_NUMBER,
            "Point size or line width; does not apply to polygons",
            TARGET_SYMBOL,
            method("setSize", "setWidth"),
            minimum=0.05,
            maximum=100.0,
            unit="mm",
        ),
        StyleProperty(
            "stroke_color",
            KIND_COLOR,
            "Colour of the stroke around a point or a polygon",
            TARGET_LAYER,
            method("setStrokeColor"),
        ),
        StyleProperty(
            "stroke_width",
            KIND_NUMBER,
            "Width of the stroke around a point or a polygon",
            TARGET_LAYER,
            method("setStrokeWidth"),
            minimum=0.0,
            maximum=20.0,
            unit="mm",
        ),
        StyleProperty(
            "stroke_style",
            KIND_ENUM,
            "Dash pattern of the line or the stroke: solid, dash, dot, "
            "dashdot, or none for no stroke at all",
            TARGET_LAYER,
            method("setStrokeStyle", "setPenStyle"),
            options=tuple(sorted(PEN_STYLES)),
        ),
        StyleProperty(
            "shape",
            KIND_ENUM,
            "Marker shape for point layers: circle, square, triangle, diamond, "
            "star, cross, pentagon, hexagon",
            TARGET_LAYER,
            method("setShape"),
            options=tuple(sorted(SHAPES)),
        ),
        StyleProperty(
            "fill_style",
            KIND_ENUM,
            "Fill hatching of a polygon: solid, none for no fill at all, "
            "horizontal, vertical, diagonal, cross, dense",
            TARGET_LAYER,
            method("setBrushStyle"),
            options=tuple(sorted(BRUSH_STYLES)),
        ),
        StyleProperty(
            "angle",
            KIND_NUMBER,
            "Rotation of the marker for point layers",
            TARGET_LAYER,
            method("setAngle"),
            minimum=-360.0,
            maximum=360.0,
            unit="degrees",
        ),
    ],
)
