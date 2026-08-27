from qgis_ai_agent.qgis_tools.common.properties import (
    KIND_BOOLEAN,
    KIND_NUMBER,
    KIND_TEXT,
    PropertySet,
    StyleProperty,
    ignored,
)

LAYER_SUBJECT = "layer in the project"
PROJECT_SUBJECT = "project"
TARGET_LAYER = "layer"
TARGET_NODE = "node"
TARGET_PLACE = "place"
TARGET_PROJECT = "project"

LAYER_PROPERTIES = PropertySet(
    LAYER_SUBJECT,
    [
        StyleProperty("name", KIND_TEXT, "New name of the layer in the project", TARGET_LAYER, ignored()),
        StyleProperty("visible", KIND_BOOLEAN, "Show the layer on the map", TARGET_NODE, ignored()),
        StyleProperty(
            "group",
            KIND_TEXT,
            "Group in the layer tree. An empty string moves the layer to the root. "
            "A group that does not exist will be created.",
            TARGET_PLACE,
            ignored(),
        ),
        StyleProperty(
            "position",
            KIND_NUMBER,
            "Position inside the group: 0 is the very top, higher layers are drawn over the rest",
            TARGET_PLACE,
            ignored(),
            minimum=0.0,
            maximum=999.0,
        ),
    ],
)

PROJECT_PROPERTIES = PropertySet(
    PROJECT_SUBJECT,
    [
        StyleProperty("title", KIND_TEXT, "Project title", TARGET_PROJECT, ignored()),
        StyleProperty(
            "crs",
            KIND_TEXT,
            "Project coordinate system such as EPSG:3857. Changes the map projection, leaves layer data alone.",
            TARGET_PROJECT,
            ignored(),
        ),
    ],
)
