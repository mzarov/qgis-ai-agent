from qgis.core import (
    Qgis,
    QgsLayoutItem,
    QgsLayoutItemMap,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
)

LAYOUT_UNIT_MM = getattr(
    QgsUnitTypes, "LayoutMillimeters", getattr(Qgis.LayoutUnit, "Millimeters", None)
)
PAGE_MARGIN_MM = 8.0


def get_layout(layout_name: str):
    """Возвращает макет по имени или выбрасывает ValueError."""
    project = QgsProject.instance()
    layout = project.layoutManager().layoutByName(layout_name)
    if not layout:
        raise ValueError(f"Макет не найден: {layout_name}")
    return layout


def get_first_map_item(layout):
    """Возвращает первый элемент карты в макете или None."""
    for item in layout.items():
        if isinstance(item, QgsLayoutItemMap):
            return item
    return None


def get_map_extent() -> QgsRectangle:
    """Extent для карты: канвас или объединение слоёв."""
    try:
        from qgis.utils import iface
        if iface and iface.mapCanvas():
            ext = iface.mapCanvas().extent()
            if ext and not ext.isEmpty():
                return ext
    except Exception:
        pass
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if hasattr(layer, "extent") and layer.extent():
            return layer.extent()
    return QgsRectangle(0, 0, 100, 100)


def get_page_size_mm(layout) -> tuple[float, float]:
    """Возвращает размер первой страницы в мм."""
    page = layout.pageCollection().page(0)
    if not page:
        return 210.0, 297.0
    size = page.pageSize()
    return float(size.width()), float(size.height())


def resolve_layout_zones(layout) -> dict[str, float]:
    """Возвращает единый policy safe-area и зон макета в мм."""
    page_width, page_height = get_page_size_mm(layout)
    margin = 10.0
    gutter = 6.0
    top_band_h = 20.0
    footer_h = 14.0
    legend_lane_w = 56.0 if page_width >= 250.0 else 0.0
    safe_x = margin
    safe_y = margin
    safe_w = max(60.0, page_width - margin * 2)
    safe_h = max(60.0, page_height - margin * 2)
    top_band_x = safe_x
    top_band_y = safe_y
    top_band_w = safe_w
    top_band_h = min(top_band_h, safe_h)
    footer_x = safe_x
    footer_h = min(footer_h, safe_h)
    footer_y = page_height - margin - footer_h
    footer_w = safe_w
    content_x = safe_x
    content_y = top_band_y + top_band_h + gutter
    content_w = safe_w - legend_lane_w
    content_h = max(60.0, footer_y - gutter - content_y)
    legend_x = safe_x + content_w + gutter if legend_lane_w > 0 else safe_x
    legend_y = content_y
    legend_w = max(42.0, legend_lane_w - gutter) if legend_lane_w > 0 else max(42.0, safe_w * 0.24)
    legend_h = content_h
    return {
        "page_width": page_width,
        "page_height": page_height,
        "margin": margin,
        "gutter": gutter,
        "safe_x": safe_x,
        "safe_y": safe_y,
        "safe_w": safe_w,
        "safe_h": safe_h,
        "top_band_h": top_band_h,
        "footer_h": footer_h,
        "legend_lane_w": legend_lane_w,
        "top_band_x": top_band_x,
        "top_band_y": top_band_y,
        "top_band_w": top_band_w,
        "footer_x": footer_x,
        "footer_y": footer_y,
        "footer_w": footer_w,
        "content_x": content_x,
        "content_y": content_y,
        "content_w": max(60.0, content_w),
        "content_h": max(60.0, content_h),
        "legend_x": legend_x,
        "legend_y": legend_y,
        "legend_w": legend_w,
        "legend_h": max(35.0, legend_h),
    }


def item_bbox_mm(item) -> tuple[float, float, float, float] | None:
    """Оценивает bbox элемента макета в мм."""
    try:
        # Предпочтительно использовать sceneBoundingRect как универсальный вариант
        rect = item.sceneBoundingRect()
        return float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height())
    except Exception:
        return None


def get_layout_item_bboxes(layout, include_maps: bool = False) -> list[tuple[float, float, float, float]]:
    """Список bbox существующих элементов макета."""
    result = []
    for item in layout.items():
        if isinstance(item, QgsLayoutItem):
            if not include_maps and isinstance(item, QgsLayoutItemMap):
                continue
            bbox = item_bbox_mm(item)
            if bbox:
                result.append(bbox)
    return result


def _intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def clamp_to_page_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    page_width: float,
    page_height: float,
    margin: float = PAGE_MARGIN_MM,
) -> tuple[float, float]:
    """Ограничивает позицию так, чтобы прямоугольник оставался внутри страницы."""
    min_x = margin
    min_y = margin
    max_x = page_width - width - margin
    max_y = page_height - height - margin

    if max_x < min_x:
        # При нехватке места в safe-area ослабляем ограничение до физической страницы.
        min_x = 0.0
        max_x = page_width - width
    if max_y < min_y:
        # При нехватке места в safe-area ослабляем ограничение до физической страницы.
        min_y = 0.0
        max_y = page_height - height

    if max_x < min_x:
        safe_x = 0.0
    else:
        safe_x = min(max(min_x, x), max_x)

    if max_y < min_y:
        safe_y = 0.0
    else:
        safe_y = min(max(min_y, y), max_y)

    return safe_x, safe_y


def clamp_to_zone_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    zone_x: float,
    zone_y: float,
    zone_width: float,
    zone_height: float,
) -> tuple[float, float]:
    """Ограничивает позицию так, чтобы элемент оставался внутри зоны."""
    min_x = zone_x
    min_y = zone_y
    max_x = zone_x + zone_width - width
    max_y = zone_y + zone_height - height
    if max_x < min_x:
        safe_x = zone_x
    else:
        safe_x = min(max(min_x, x), max_x)
    if max_y < min_y:
        safe_y = zone_y
    else:
        safe_y = min(max(min_y, y), max_y)
    return safe_x, safe_y


def is_inside_page_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    page_width: float,
    page_height: float,
    margin: float = PAGE_MARGIN_MM,
) -> bool:
    """Проверяет, что прямоугольник полностью внутри рабочей области страницы."""
    return (
        x >= margin
        and y >= margin
        and x + width <= page_width - margin
        and y + height <= page_height - margin
    )


def find_non_overlapping_position(
    layout,
    x: float,
    y: float,
    width: float,
    height: float,
    page_width: float,
    page_height: float,
    include_maps: bool = False,
    margin: float = PAGE_MARGIN_MM,
) -> tuple[float, float]:
    """Ищет ближайшую позицию без пересечений, начиная с (x, y)."""
    existing = get_layout_item_bboxes(layout, include_maps=include_maps)
    step = 6.0
    max_tries = 80
    px, py = clamp_to_page_bounds(x, y, width, height, page_width, page_height, margin=margin)

    for i in range(max_tries):
        px, py = clamp_to_page_bounds(
            px, py, width, height, page_width, page_height, margin=margin
        )
        candidate = (px, py, width, height)
        if (
            is_inside_page_bounds(px, py, width, height, page_width, page_height, margin=margin)
            and not any(_intersects(candidate, e) for e in existing)
        ):
            return px, py

        py += step
        px, py = clamp_to_page_bounds(px, py, width, height, page_width, page_height, margin=margin)

        if py + height > page_height - margin:
            start_y = margin + (i % 5) * step
            py = start_y
            px += step

    fallback_x, fallback_y = clamp_to_page_bounds(
        px, py, width, height, page_width, page_height, margin=margin
    )
    if is_inside_page_bounds(
        fallback_x, fallback_y, width, height, page_width, page_height, margin=margin
    ):
        return fallback_x, fallback_y

    # Если элемент физически не помещается в safe-area, возвращаем точку внутри страницы.
    return clamp_to_page_bounds(
        fallback_x, fallback_y, width, height, page_width, page_height, margin=0.0
    )


def place_item_with_policy(
    layout,
    x: float,
    y: float,
    width: float,
    height: float,
    page_width: float,
    page_height: float,
    zone_x: float,
    zone_y: float,
    zone_width: float,
    zone_height: float,
    include_maps: bool = False,
    margin: float = PAGE_MARGIN_MM,
    keep_y: bool = False,
    use_overlap_search: bool = True,
) -> tuple[float, float]:
    """Единый pipeline размещения: clamp -> anti-overlap -> final clamp."""
    base_x, base_y = clamp_to_page_bounds(
        x,
        y,
        width,
        height,
        page_width,
        page_height,
        margin=margin,
    )
    base_x, base_y = clamp_to_zone_bounds(
        base_x,
        base_y,
        width,
        height,
        zone_x,
        zone_y,
        zone_width,
        zone_height,
    )
    if not use_overlap_search:
        return base_x, base_y
    safe_x, safe_y = find_non_overlapping_position(
        layout=layout,
        x=base_x,
        y=base_y,
        width=width,
        height=height,
        page_width=page_width,
        page_height=page_height,
        include_maps=include_maps,
        margin=margin,
    )
    safe_x, safe_y = clamp_to_page_bounds(
        safe_x,
        safe_y,
        width,
        height,
        page_width,
        page_height,
        margin=margin,
    )
    safe_x, safe_y = clamp_to_zone_bounds(
        safe_x,
        safe_y,
        width,
        height,
        zone_x,
        zone_y,
        zone_width,
        zone_height,
    )
    if keep_y:
        safe_y = base_y
    return safe_x, safe_y
