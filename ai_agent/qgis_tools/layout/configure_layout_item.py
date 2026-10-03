from contextlib import suppress
from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.layout.items import (
    ITEM_LABEL,
    ITEM_LEGEND,
    apply_label_text,
    check_bounds,
    describe_item,
    find_item,
    item_kind,
    place,
)
from ai_agent.qgis_tools.layout.pages import find_layout

MOVABLE_KEYS = ("x", "y", "width", "height")
PROPERTY_KEYS = {ITEM_LABEL: ("text", "font_size"), ITEM_LEGEND: ("title",)}


class ConfigureLayoutItemTool(BaseTool):
    name = "configure_layout_item"
    description = (
        "Move, resize or retitle an existing layout item found by its id: new "
        "position and size in millimetres, new text for a label, new title for "
        "a legend. Use it to fix what the verification found."
    )
    skill = "layout"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "The item id must exist (see describe_layout)",
        "The new frame must stay inside the page",
    ]
    examples = ["Move the legend so it does not cover the map", "Make the title bigger"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
        {
            "name": "item_id",
            "type": "string",
            "description": "Item id exactly as in describe_layout",
            "required": True,
        },
        {"name": "x", "type": "number", "description": "New left edge, mm", "required": False},
        {"name": "y", "type": "number", "description": "New top edge, mm", "required": False},
        {"name": "width", "type": "number", "description": "New width, mm", "required": False},
        {"name": "height", "type": "number", "description": "New height, mm", "required": False},
        {
            "name": "properties",
            "type": "object",
            "description": "label: {text, font_size}; legend: {title}",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        item = find_item(layout, params.get("item_id") or "")
        frame = _merged_frame(item, params)
        if frame is not None:
            check_bounds(layout, *frame)
        properties = params.get("properties")
        if isinstance(properties, dict) and properties:
            _check_properties(item_kind(item), properties)
        elif frame is None:
            raise ValueError("Nothing to change: give a new position, size or properties.")
        prepared = dict(params)
        prepared["layout_name"] = layout.name()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        item_id = (params.get("item_id") or "").strip()
        name = (params.get("layout_name") or "").strip()
        return tr("Changing item '{0}' of layout '{1}'.").format(item_id, name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        item = find_item(layout, params.get("item_id") or "")
        frame = _merged_frame(item, params)
        properties = params.get("properties")
        # Properties go first: they are the step that can still fail, and a
        # refused change must not leave the item moved but not retitled.
        if isinstance(properties, dict) and properties:
            _check_properties(item_kind(item), properties)
            _apply_properties(item, properties)
        if frame is not None:
            place(item, *frame)
        return {"layout": layout.name(), "item": describe_item(item)}


def _merged_frame(item: Any, params: dict[str, Any]) -> tuple[float, float, float, float] | None:
    if not any(params.get(key) is not None for key in MOVABLE_KEYS):
        return None
    current = describe_item(item)
    values = []
    for key in MOVABLE_KEYS:
        raw = params.get(key)
        if raw is None:
            raw = current.get(key, 0.0)
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number in millimetres.") from None
    return values[0], values[1], values[2], values[3]


def _check_properties(kind: str, properties: dict[str, Any]) -> None:
    allowed = PROPERTY_KEYS.get(kind, ())
    unknown = sorted(str(key) for key in properties if key not in allowed)
    if unknown:
        accepted = ", ".join(allowed) if allowed else "no properties (only position and size)"
        target = f"a {kind} item" if kind else "this item"
        raise ValueError(
            f"Properties {', '.join(unknown)} do not apply to {target}; it accepts {accepted}. "
            "A label takes text and font_size, a legend takes title."
        )
    if "font_size" in properties:
        try:
            size = float(properties["font_size"])
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            raise ValueError("font_size must be a positive number of points.")


def _apply_properties(item: Any, properties: dict[str, Any]) -> None:
    kind = item_kind(item)
    if kind == ITEM_LABEL and ("text" in properties or "font_size" in properties):
        current = ""
        with suppress(Exception):
            current = str(item.text() or "")
        apply_label_text(item, str(properties.get("text", current) or current), properties.get("font_size"))
    if kind == ITEM_LEGEND and str(properties.get("title") or "").strip():
        item.setTitle(str(properties["title"]).strip())
