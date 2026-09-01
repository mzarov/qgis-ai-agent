from contextlib import suppress
from typing import Any

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsTextFormat,
)

from ai_agent.qgis_tools.layout.pages import current_page_mm

ITEM_MAP = "map"
ITEM_LEGEND = "legend"
ITEM_SCALE_BAR = "scale_bar"
ITEM_LABEL = "label"
ITEM_NORTH_ARROW = "north_arrow"
ITEM_PICTURE = "picture"
ITEM_TYPES = (ITEM_MAP, ITEM_LEGEND, ITEM_SCALE_BAR, ITEM_LABEL, ITEM_NORTH_ARROW, ITEM_PICTURE)
TYPE_CLASSES = {
    ITEM_MAP: QgsLayoutItemMap,
    ITEM_LEGEND: QgsLayoutItemLegend,
    ITEM_SCALE_BAR: QgsLayoutItemScaleBar,
    ITEM_LABEL: QgsLayoutItemLabel,
    ITEM_NORTH_ARROW: QgsLayoutItemPicture,
    ITEM_PICTURE: QgsLayoutItemPicture,
}
NORTH_ARROWS = {
    "simple": "arrows/NorthArrow_02.svg",
    "compass": "arrows/NorthArrow_04.svg",
    "triangle": "arrows/NorthArrow_11.svg",
}
DEFAULT_NORTH_ARROW = "simple"
SCALE_BAR_STYLES = {
    "single_box": "Single Box",
    "double_box": "Double Box",
    "ticks": "Line Ticks Middle",
    "numeric": "Numeric",
}
DEFAULT_SIZES_MM = {
    ITEM_MAP: (180.0, 150.0),
    ITEM_LEGEND: (50.0, 60.0),
    ITEM_SCALE_BAR: (60.0, 12.0),
    ITEM_LABEL: (120.0, 12.0),
    ITEM_NORTH_ARROW: (18.0, 18.0),
    ITEM_PICTURE: (40.0, 40.0),
}
MM = getattr(getattr(Qgis, "LayoutUnit", None), "Millimeters", None)


def item_kind(item: Any) -> str:
    if isinstance(item, QgsLayoutItemPicture):
        return ITEM_NORTH_ARROW if _is_north_arrow(item) else ITEM_PICTURE
    for kind, klass in TYPE_CLASSES.items():
        if isinstance(item, klass):
            return kind
    return ""


def _is_north_arrow(item: Any) -> bool:
    try:
        return "northarrow" in str(item.picturePath() or "").lower().replace("_", "")
    except Exception:
        return False


def north_arrow_path(style: str) -> str:
    wanted = (style or DEFAULT_NORTH_ARROW).strip().lower()
    if wanted not in NORTH_ARROWS:
        raise ValueError(f"Unknown north arrow style '{style}'. Available: {', '.join(sorted(NORTH_ARROWS))}.")
    return QgsApplication.svgPaths()[0] + "/" + NORTH_ARROWS[wanted] if QgsApplication.svgPaths() else ""


def layout_items(layout: Any) -> list[Any]:
    found = []
    for item in layout.items():
        if item_kind(item):
            found.append(item)
    return found


def find_item(layout: Any, item_id: str) -> Any:
    wanted = (item_id or "").strip()
    for item in layout_items(layout):
        if str(item.id() or "") == wanted:
            return item
    known = ", ".join(f"'{item.id()}'" for item in layout_items(layout) if item.id())
    hint = known or "the layout has no addressable items"
    raise ValueError(f"No item with id '{wanted}' in this layout. Available: {hint}.")


def unique_item_id(layout: Any, kind: str, given: str) -> str:
    wanted = (given or "").strip()
    taken = {str(item.id() or "") for item in layout_items(layout)}
    if wanted:
        if wanted in taken:
            raise ValueError(f"An item with id '{wanted}' already exists in this layout.")
        return wanted
    number = 1
    while f"{kind}-{number}" in taken:
        number += 1
    return f"{kind}-{number}"


def place(item: Any, x: float, y: float, width: float, height: float) -> None:
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    item.attemptResize(QgsLayoutSize(width, height, MM))


def describe_item(item: Any) -> dict[str, Any]:
    described: dict[str, Any] = {"id": str(item.id() or ""), "type": item_kind(item)}
    with suppress(Exception):
        rect = item.sceneBoundingRect()
        described.update(
            {
                "x": round(float(rect.x()), 1),
                "y": round(float(rect.y()), 1),
                "width": round(float(rect.width()), 1),
                "height": round(float(rect.height()), 1),
            }
        )
    if item_kind(item) == ITEM_LABEL:
        with suppress(Exception):
            described["text"] = str(item.text() or "")
    return described


def check_bounds(layout: Any, x: float, y: float, width: float, height: float) -> None:
    page_width, page_height = current_page_mm(layout)
    if x < 0 or y < 0 or x + width > page_width or y + height > page_height:
        raise ValueError(
            f"The item ({x};{y} size {width}x{height} mm) sticks out of the "
            f"{page_width}x{page_height} mm page. Keep it inside, with margins around 10 mm."
        )


def apply_label_text(item: Any, text: str, font_size: Any) -> None:
    item.setText(text)
    size = _as_float(font_size)
    if size is None:
        return
    with suppress(Exception):
        text_format = QgsTextFormat()
        text_format.setSize(size)
        item.setTextFormat(text_format)


def first_map(layout: Any) -> Any:
    for item in layout_items(layout):
        if item_kind(item) == ITEM_MAP:
            return item
    return None


def linked_map(layout: Any, properties: dict[str, Any]) -> Any:
    wanted = str(properties.get("map_id") or "").strip()
    if wanted:
        item = find_item(layout, wanted)
        if item_kind(item) != ITEM_MAP:
            raise ValueError(f"Item '{wanted}' is a {item_kind(item)}, not a map.")
        return item
    found = first_map(layout)
    if found is None:
        raise ValueError("The layout has no map yet — add a map item first, then link to it.")
    return found


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
