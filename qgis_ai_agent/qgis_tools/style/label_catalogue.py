from qgis_ai_agent.qgis_tools.common.properties import (
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

SUBJECT = "labels"
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
        StyleProperty(
            "field",
            KIND_TEXT,
            "Field whose values label the features",
            TARGET_SETTINGS,
            setter("fieldName"),
        ),
        StyleProperty(
            "enabled",
            KIND_BOOLEAN,
            "false switches the layer labels off entirely",
            TARGET_SETTINGS,
            ignored(),
        ),
        StyleProperty(
            "font",
            KIND_TEXT,
            "Font family, for example Arial or Times New Roman",
            TARGET_FONT,
            method("setFamily"),
        ),
        StyleProperty("bold", KIND_BOOLEAN, "Bold weight", TARGET_FONT, method("setBold")),
        StyleProperty("italic", KIND_BOOLEAN, "Italic", TARGET_FONT, method("setItalic")),
        StyleProperty(
            "size",
            KIND_NUMBER,
            "Font size",
            TARGET_FORMAT,
            method("setSize"),
            minimum=3.0,
            maximum=72.0,
            unit="points",
        ),
        StyleProperty("color", KIND_COLOR, "Colour of the text itself", TARGET_FORMAT, method("setColor")),
        StyleProperty(
            "opacity",
            KIND_NUMBER,
            "Opacity of the label: 1 is fully opaque",
            TARGET_FORMAT,
            method("setOpacity"),
            minimum=0.0,
            maximum=1.0,
        ),
        StyleProperty(
            "buffer",
            KIND_BOOLEAN,
            "Buffer (halo) around the text: false removes it",
            TARGET_BUFFER,
            ignored(),
        ),
        StyleProperty(
            "buffer_color",
            KIND_COLOR,
            "Colour of the text buffer, usually white",
            TARGET_BUFFER,
            method("setColor"),
        ),
        StyleProperty(
            "buffer_size",
            KIND_NUMBER,
            "Thickness of the text buffer",
            TARGET_BUFFER,
            method("setSize"),
            minimum=0.1,
            maximum=10.0,
            unit="mm",
        ),
        StyleProperty(
            "offset_x",
            KIND_NUMBER,
            "Offset of the label to the right of the anchor point",
            TARGET_SETTINGS,
            setter("xOffset"),
            minimum=-100.0,
            maximum=100.0,
            unit="mm",
        ),
        StyleProperty(
            "offset_y",
            KIND_NUMBER,
            "Offset of the label below the anchor point; upwards is a negative number",
            TARGET_SETTINGS,
            setter("yOffset"),
            minimum=-100.0,
            maximum=100.0,
            unit="mm",
        ),
        StyleProperty(
            "distance",
            KIND_NUMBER,
            "Gap between the label and the geometry itself",
            TARGET_SETTINGS,
            setter("dist"),
            minimum=0.0,
            maximum=100.0,
            unit="mm",
        ),
        StyleProperty(
            "rotation",
            KIND_NUMBER,
            "Rotation of the label",
            TARGET_SETTINGS,
            setter("angleOffset"),
            minimum=-360.0,
            maximum=360.0,
            unit="degrees",
        ),
        StyleProperty(
            "placement",
            KIND_ENUM,
            "How the label sits relative to the feature: over for centred, around for "
            "around the point, horizontal, curved to follow a curved line, "
            "line along the line, outside for outside the polygon",
            TARGET_SETTINGS,
            setter("placement"),
            options=tuple(sorted(PLACEMENTS)),
        ),
        StyleProperty("shadow", KIND_BOOLEAN, "Shadow under the label: false removes it", TARGET_SHADOW, ignored()),
        StyleProperty(
            "shadow_color",
            KIND_COLOR,
            "Colour of the shadow under the label",
            TARGET_SHADOW,
            method("setColor"),
        ),
        StyleProperty(
            "background",
            KIND_BOOLEAN,
            "Background behind the label: false removes it",
            TARGET_BACKGROUND,
            ignored(),
        ),
        StyleProperty(
            "background_color",
            KIND_COLOR,
            "Colour of the background behind the label",
            TARGET_BACKGROUND,
            method("setFillColor"),
        ),
    ],
)
