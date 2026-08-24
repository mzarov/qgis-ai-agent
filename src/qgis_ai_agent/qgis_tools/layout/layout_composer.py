from qgis.core import QgsLayoutPoint, QgsLayoutSize

from qgis_ai_agent.qgis_tools.layout.utils import (
    LAYOUT_UNIT_MM,
    place_item_with_policy,
    resolve_layout_zones,
)


def pick_title_font_size(text: str, page_width_mm: float) -> float:
    """Подбирает размер заголовка по длине текста и ширине страницы."""
    length = max(1, len((text or "").strip()))
    if page_width_mm >= 380:
        base = 22.0
    elif page_width_mm >= 280:
        base = 18.0
    else:
        base = 15.0
    if length > 70:
        base -= 5
    elif length > 45:
        base -= 3
    elif length > 30:
        base -= 1.5
    return max(9.0, base)


def build_layout_policy(layout) -> dict[str, float]:
    """Единые зоны и отступы для макетирования."""
    return resolve_layout_zones(layout)


def compose_map_box(layout, x: float | None, y: float | None, width: float | None, height: float | None) -> dict[str, float]:
    """Рекомендуемая зона карты в рамках page safe-area."""
    policy = build_layout_policy(layout)
    margin = policy["margin"]
    map_x = float(x) if x is not None else policy["content_x"]
    map_y = float(y) if y is not None else policy["content_y"]
    map_w = float(width) if width is not None else policy["content_w"]
    map_h = float(height) if height is not None else policy["content_h"]
    map_x, map_y = place_item_with_policy(
        layout=layout,
        x=map_x,
        y=map_y,
        width=map_w,
        height=map_h,
        page_width=policy["page_width"],
        page_height=policy["page_height"],
        zone_x=policy["content_x"],
        zone_y=policy["content_y"],
        zone_width=policy["content_w"],
        zone_height=policy["content_h"],
        include_maps=False,
        margin=margin,
        use_overlap_search=True,
    )
    return {"x": map_x, "y": map_y, "width": map_w, "height": map_h}


def compose_legend_box(layout, x: float | None, y: float | None, width: float | None, height: float | None) -> dict[str, float]:
    """Рекомендуемая зона легенды в правой панели или подстраиваемая по странице."""
    policy = build_layout_policy(layout)
    margin = policy["margin"]
    default_w = float(width) if width is not None else min(policy["legend_w"], 58.0)
    default_h = float(height) if height is not None else max(35.0, min(policy["legend_h"] * 0.45, 90.0))
    base_x = float(x) if x is not None else policy["legend_x"]
    base_y = float(y) if y is not None else policy["legend_y"]
    safe_x, safe_y = place_item_with_policy(
        layout=layout,
        x=base_x,
        y=base_y,
        width=default_w,
        height=default_h,
        page_width=policy["page_width"],
        page_height=policy["page_height"],
        zone_x=policy["legend_x"],
        zone_y=policy["legend_y"],
        zone_width=policy["legend_w"],
        zone_height=policy["legend_h"],
        include_maps=False,
        margin=margin,
    )
    return {"x": safe_x, "y": safe_y, "width": default_w, "height": default_h}


def compose_label_box(
    layout,
    role: str,
    text: str,
    alignment: str,
    x: float | None,
    y: float | None,
) -> dict[str, float]:
    """
    Возвращает рекомендуемый бокс надписи (x, y, width, height, font_size).
    role: title/subtitle/footer/label
    """
    policy = build_layout_policy(layout)
    page_width = policy["page_width"]
    page_height = policy["page_height"]
    margin = policy["margin"]
    role = (role or "label").lower()
    alignment = (alignment or "left").lower()
    if alignment in {"top-center", "middle", "centre"}:
        alignment = "center"

    if role == "title":
        # Заголовок всегда размещаем как top-center, независимо от входных x/y.
        alignment = "center"
        width = max(80.0, page_width - margin * 2)
        # Для длинных заголовков резервируем высоту под 2 строки.
        estimated_lines = 2 if len((text or "").strip()) > 42 or "\n" in (text or "") else 1
        height = max(14.0, policy["top_band_h"] - 4.0)
        if estimated_lines > 1:
            height = max(height, 22.0)
        font_size = pick_title_font_size(text, page_width)
        base_x = (page_width - width) / 2.0
        # Заголовок всегда стартует в верхней зоне.
        base_y = policy["top_band_y"]
    elif role == "footer":
        width = max(80.0, page_width - margin * 2)
        height = 10.0
        font_size = 8.5
        base_x = margin
        base_y = page_height - policy["footer_h"] - margin + 2.0
    else:
        width = min(max(60.0, page_width * 0.45), page_width - margin * 2)
        if role == "subtitle":
            estimated_lines = 2 if len((text or "").strip()) > 52 or "\n" in (text or "") else 1
            height = 18.0 if estimated_lines > 1 else 12.0
        else:
            height = 10.0
        font_size = 10.0
        base_x = margin if alignment != "center" else (page_width - width) / 2
        base_y = policy["content_y"] + (4.0 if role == "subtitle" else 14.0)

    if role == "title":
        target_x = base_x
        target_y = base_y
    else:
        target_x = float(x) if x is not None else base_x
        target_y = float(y) if y is not None else base_y
    if role == "title":
        safe_x, safe_y = place_item_with_policy(
            layout=layout,
            x=target_x,
            y=target_y,
            width=width,
            height=height,
            page_width=page_width,
            page_height=page_height,
            zone_x=policy["top_band_x"],
            zone_y=policy["top_band_y"],
            zone_width=policy["top_band_w"],
            zone_height=policy["top_band_h"],
            include_maps=False,
            margin=margin,
            keep_y=True,
            use_overlap_search=True,
        )
    elif role == "footer":
        safe_x, safe_y = place_item_with_policy(
            layout=layout,
            x=target_x,
            y=target_y,
            width=width,
            height=height,
            page_width=page_width,
            page_height=page_height,
            zone_x=policy["footer_x"],
            zone_y=policy["footer_y"],
            zone_width=policy["footer_w"],
            zone_height=policy["footer_h"],
            include_maps=False,
            margin=margin,
            use_overlap_search=True,
        )
    else:
        safe_x, safe_y = place_item_with_policy(
            layout=layout,
            x=target_x,
            y=target_y,
            width=width,
            height=height,
            page_width=page_width,
            page_height=page_height,
            zone_x=policy["content_x"],
            zone_y=policy["content_y"],
            zone_width=policy["content_w"],
            zone_height=policy["content_h"],
            include_maps=False,
            margin=margin,
        )
    return {
        "x": safe_x,
        "y": safe_y,
        "width": width,
        "height": height,
        "font_size": font_size,
        "alignment": alignment,
    }


def apply_label_geometry(label, box: dict[str, float]) -> None:
    """Применяет геометрию и размер блока к label."""
    label.attemptResize(QgsLayoutSize(box["width"], box["height"], LAYOUT_UNIT_MM))
    label.attemptMove(QgsLayoutPoint(box["x"], box["y"], LAYOUT_UNIT_MM))
