from qgis_ai_agent.qgis_tools.common.properties import (
    KIND_BOOLEAN,
    KIND_NUMBER,
    KIND_TEXT,
    PropertySet,
    StyleProperty,
    ignored,
)

LAYER_SUBJECT = "слой в проекте"
PROJECT_SUBJECT = "проект"
TARGET_LAYER = "layer"
TARGET_NODE = "node"
TARGET_PLACE = "place"
TARGET_PROJECT = "project"

LAYER_PROPERTIES = PropertySet(
    LAYER_SUBJECT,
    [
        StyleProperty("name", KIND_TEXT, "Новое имя слоя в проекте", TARGET_LAYER, ignored()),
        StyleProperty("visible", KIND_BOOLEAN, "Показывать слой на карте", TARGET_NODE, ignored()),
        StyleProperty(
            "group",
            KIND_TEXT,
            "Группа в дереве слоёв. Пустая строка — вынести в корень. "
            "Отсутствующая группа будет создана.",
            TARGET_PLACE,
            ignored(),
        ),
        StyleProperty(
            "position",
            KIND_NUMBER,
            "Позиция внутри группы: 0 — самый верх, выше рисуется поверх остальных",
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
        StyleProperty("title", KIND_TEXT, "Название проекта", TARGET_PROJECT, ignored()),
        StyleProperty(
            "crs",
            KIND_TEXT,
            "Система координат проекта в виде EPSG:3857. Меняет проекцию карты, "
            "данные слоёв не трогает.",
            TARGET_PROJECT,
            ignored(),
        ),
    ],
)
