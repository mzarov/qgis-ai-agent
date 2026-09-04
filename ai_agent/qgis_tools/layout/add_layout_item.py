import os
from contextlib import suppress
from math import isfinite
from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import canvas_extent, find_layer_by_name, safe_extent
from ai_agent.qgis_tools.layout.items import (
    DEFAULT_NORTH_ARROW,
    DEFAULT_SIZES_MM,
    ITEM_LABEL,
    ITEM_LEGEND,
    ITEM_MAP,
    ITEM_NORTH_ARROW,
    ITEM_PICTURE,
    ITEM_SCALE_BAR,
    ITEM_TYPES,
    NORTH_ARROWS,
    SCALE_BAR_STYLES,
    TYPE_CLASSES,
    apply_label_text,
    check_bounds,
    linked_map,
    north_arrow_path,
    place,
    unique_item_id,
)
from ai_agent.qgis_tools.layout.pages import find_layout

CANVAS = "canvas"
DEGENERATE_PADDING_RATIO = 0.05
POINT_PADDING_DEGREES = 0.01
POINT_PADDING_MAP_UNITS = 1.0


class AddLayoutItemTool(BaseTool):
    name = "add_layout_item"
    description = (
        "Add one item to a print layout: a map, a legend, a scale bar or a text "
        "label. Position and size are millimetres from the top-left page corner. "
        "Type-specific settings go into the properties object."
    )
    skill = "layout"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "The layout must exist; the item must fit inside the page",
        "A label requires properties.text; a legend and a scale bar need a map in the layout",
    ]
    examples = ["Add a map over most of the page", "Put the title at the top"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
        {
            "name": "item_type",
            "type": "string",
            "enum": list(ITEM_TYPES),
            "description": "What to add",
            "required": True,
        },
        {"name": "x", "type": "number", "description": "Left edge, mm", "required": True},
        {"name": "y", "type": "number", "description": "Top edge, mm", "required": True},
        {"name": "width", "type": "number", "description": "Width, mm (type default when omitted)", "required": False},
        {
            "name": "height",
            "type": "number",
            "description": "Height, mm (type default when omitted)",
            "required": False,
        },
        {
            "name": "id",
            "type": "string",
            "description": "Item id for later changes; auto like map-1 when omitted",
            "required": False,
        },
        {
            "name": "properties",
            "type": "object",
            "description": (
                "Type-specific settings. label: {text, font_size}. "
                "map: {extent: 'canvas' or a layer name}. "
                "legend: {title, map_id}. "
                f"scale_bar: {{style: {'/'.join(sorted(SCALE_BAR_STYLES))}, map_id}}. "
                f"north_arrow: {{style: {'/'.join(sorted(NORTH_ARROWS))}}}. "
                "picture: {path: an image file on disk}."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        kind = _checked_kind(params.get("item_type"))
        properties = _checked_properties(kind, params.get("properties"))
        x, y, width, height = _frame(params, kind)
        check_bounds(layout, x, y, width, height)
        if kind == ITEM_MAP:
            _map_view(properties)
        prepared = dict(params)
        prepared["layout_name"] = layout.name()
        prepared["item_type"] = kind
        prepared["width"] = width
        prepared["height"] = height
        prepared["id"] = unique_item_id(layout, kind, str(params.get("id") or ""))
        prepared["properties"] = properties
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        kind = str(params.get("item_type") or "").strip()
        name = (params.get("layout_name") or "").strip()
        return tr("Adding a {0} to layout '{1}'.").format(kind, name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        kind = _checked_kind(params.get("item_type"))
        properties = _checked_properties(kind, params.get("properties"))
        x, y, width, height = _frame(params, kind)
        check_bounds(layout, x, y, width, height)
        map_view = _map_view(properties) if kind == ITEM_MAP else None
        identifier = unique_item_id(layout, kind, str(params.get("id") or ""))
        item = TYPE_CLASSES[kind](layout)
        item.setId(identifier)
        _configure(layout, item, kind, properties)
        if map_view is not None and map_view[1] is not None:
            item.setCrs(map_view[1])
        try:
            layout.addLayoutItem(item)
            place(item, x, y, width, height)
            if map_view is not None:
                _zoom_map(item, map_view[0])
        except Exception:
            layout.removeLayoutItem(item)
            raise
        return {"layout": layout.name(), "id": str(item.id()), "type": kind}


def _checked_kind(raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in ITEM_TYPES:
        raise ValueError(f"Unknown item type '{raw}'. Available: {', '.join(ITEM_TYPES)}.")
    return kind


def _checked_properties(kind: str, raw: Any) -> dict[str, Any]:
    properties = dict(raw) if isinstance(raw, dict) else {}
    if kind == ITEM_LABEL and not str(properties.get("text") or "").strip():
        raise ValueError("A label needs properties.text — the words to put on the page.")
    style = str(properties.get("style") or "").strip().lower()
    if kind == ITEM_SCALE_BAR and style and style not in SCALE_BAR_STYLES:
        raise ValueError(f"Unknown scale bar style '{style}'. Available: {', '.join(sorted(SCALE_BAR_STYLES))}.")
    if kind == ITEM_NORTH_ARROW and style and style not in NORTH_ARROWS:
        raise ValueError(f"Unknown north arrow style '{style}'. Available: {', '.join(sorted(NORTH_ARROWS))}.")
    if kind == ITEM_PICTURE:
        path = str(properties.get("path") or "").strip()
        if not path:
            raise ValueError("A picture needs properties.path — the image file to place on the page.")
        if not os.path.isfile(path):
            raise ValueError(f"There is no file '{path}' on disk. Check the path.")
    return properties


def _frame(params: dict[str, Any], kind: str) -> tuple[float, float, float, float]:
    default_width, default_height = DEFAULT_SIZES_MM[kind]
    try:
        x = float(params.get("x"))
        y = float(params.get("y"))
    except (TypeError, ValueError):
        raise ValueError("x and y are required numbers in millimetres.") from None
    width = _size(params.get("width"), default_width)
    height = _size(params.get("height"), default_height)
    return x, y, width, height


def _size(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _configure(layout: Any, item: Any, kind: str, properties: dict[str, Any]) -> None:
    if kind == ITEM_MAP:
        item.setFrameEnabled(True)
    elif kind == ITEM_LABEL:
        apply_label_text(item, str(properties.get("text") or ""), properties.get("font_size"))
    elif kind == ITEM_LEGEND:
        item.setLinkedMap(linked_map(layout, properties))
        title = str(properties.get("title") or "").strip()
        if title:
            item.setTitle(title)
    elif kind == ITEM_SCALE_BAR:
        item.setLinkedMap(linked_map(layout, properties))
        style = str(properties.get("style") or "single_box").strip().lower()
        item.setStyle(SCALE_BAR_STYLES.get(style, SCALE_BAR_STYLES["single_box"]))
        _apply_default_scale(item)
    elif kind == ITEM_NORTH_ARROW:
        _configure_north_arrow(layout, item, properties)
    elif kind == ITEM_PICTURE:
        item.setPicturePath(str(properties.get("path") or "").strip())


def _zoom_map(item: Any, extent: QgsRectangle) -> None:
    try:
        item.zoomToExtent(extent)
    except Exception:
        item.setExtent(extent)


def _map_view(properties: dict[str, Any]) -> tuple[QgsRectangle, QgsCoordinateReferenceSystem | None]:
    wanted = str(properties.get("extent") or CANVAS).strip()
    if wanted.lower() == CANVAS:
        return canvas_extent(), None
    layer = find_layer_by_name(wanted)
    extent = safe_extent(layer)
    if isinstance(layer, QgsVectorLayer) and (not layer.isSpatial() or layer.featureCount() == 0):
        raise ValueError(f"Layer '{wanted}' has no spatial features to show in a map.")
    if extent is None or not _finite_extent(extent):
        raise ValueError(f"Layer '{wanted}' has no extent — it may be empty.")
    source_crs = layer.crs()
    if not source_crs.isValid():
        raise ValueError(f"Layer '{wanted}' has no valid CRS. Assign its coordinate system before creating a map.")
    if extent.isEmpty():
        if not isinstance(layer, QgsVectorLayer) or not _has_spatial_features(layer):
            raise ValueError(f"Layer '{wanted}' has no spatial features to show in a map.")
        extent = _padded_extent(extent, source_crs.isGeographic())
    project = QgsProject.instance()
    target_crs = project.crs() if project.crs().isValid() else source_crs
    if source_crs != target_crs:
        extent = QgsCoordinateTransform(source_crs, target_crs, project).transformBoundingBox(extent)
    if not _finite_extent(extent) or extent.isEmpty():
        raise ValueError(f"Layer '{wanted}' cannot be displayed in the map coordinate system.")
    return extent, target_crs


def _has_spatial_features(layer: QgsVectorLayer) -> bool:
    return any(feature.hasGeometry() and not feature.geometry().isEmpty() for feature in layer.getFeatures())


def _finite_extent(extent: QgsRectangle) -> bool:
    return all(
        isfinite(value) for value in (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    )


def _padded_extent(extent: QgsRectangle, geographic: bool) -> QgsRectangle:
    minimum = POINT_PADDING_DEGREES if geographic else POINT_PADDING_MAP_UNITS
    padding = max(extent.width(), extent.height()) * DEGENERATE_PADDING_RATIO
    padding = max(padding, minimum)
    x_padding = padding if extent.width() <= 0 else 0.0
    y_padding = padding if extent.height() <= 0 else 0.0
    return QgsRectangle(
        extent.xMinimum() - x_padding,
        extent.yMinimum() - y_padding,
        extent.xMaximum() + x_padding,
        extent.yMaximum() + y_padding,
    )


def _configure_north_arrow(layout: Any, item: Any, properties: dict[str, Any]) -> None:
    path = north_arrow_path(str(properties.get("style") or DEFAULT_NORTH_ARROW))
    if path:
        item.setPicturePath(path)
    with suppress(Exception):
        item.setLinkedMap(linked_map(layout, properties))


def _apply_default_scale(item: Any) -> None:
    with suppress(Exception):
        item.applyDefaultSize()
