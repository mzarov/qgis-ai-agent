from qgis_ai_agent.qgis_tools.layout.layout_composer import build_layout_policy
from qgis_ai_agent.qgis_tools.layout.utils import place_item_with_policy


def _nice_step(value: float) -> float:
    """Округляет число к удобному ряду 1/2/5 * 10^n."""
    if value <= 0:
        return 1.0
    import math

    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    if fraction <= 1:
        nice = 1
    elif fraction <= 2:
        nice = 2
    elif fraction <= 5:
        nice = 5
    else:
        nice = 10
    return float(nice * (10 ** exponent))


def compose_scalebar_params(
    layout,
    map_item,
    x: float | None,
    y: float | None,
    preferred_units: str | None = None,
) -> dict[str, float | str]:
    """Подбирает читаемые параметры линейки по масштабу и размеру карты."""
    policy = build_layout_policy(layout)
    page_width = policy["page_width"]
    page_height = policy["page_height"]
    margin = policy["margin"]
    map_width_mm = max(20.0, float(map_item.rect().width()))

    # Целевая длина линейки рассчитывается от реальной карты,
    # но строго ограничивается рабочей шириной страницы.
    max_allowed = max(40.0, page_width - margin * 2)
    target_length_mm = min(max_allowed, max(28.0, map_width_mm * 0.30))

    scale_value = 0.0
    try:
        scale_value = float(map_item.scale())
    except Exception:
        scale_value = 25000.0
    if scale_value <= 0:
        scale_value = 25000.0

    # Простая аппроксимация: 1 мм на листе ~ scale/1000 метров на местности.
    meters_per_mm = scale_value / 1000.0
    meters_for_bar = max(50.0, target_length_mm * meters_per_mm)

    units = (preferred_units or "").lower().strip()
    if not units:
        units = "km" if meters_for_bar >= 1500 else "m"

    # На крупных картах принудительно переключаемся в km, чтобы подписи не слипались.
    if units in ("m", "meters", "метры") and meters_for_bar >= 8000:
        units = "km"

    if units == "km":
        total_units = meters_for_bar / 1000.0
    else:
        total_units = meters_for_bar

    # Целимся в 3 деления, но подстраиваемся под читаемость подписей.
    preferred_segments = 3
    units_per_segment = _nice_step(total_units / preferred_segments)

    if units == "km":
        units_per_segment = max(1.0, min(units_per_segment, 400.0))
    else:
        units_per_segment = max(20.0, min(units_per_segment, 10000.0))

    segment_count = 5
    # Эвристика против слипшегося текста: длинные подписи -> меньше делений.
    max_label_value = units_per_segment * segment_count
    label_len = len(f"{int(max_label_value):,}".replace(",", " "))
    if label_len >= 8:
        segment_count = 4
    if label_len >= 10:
        segment_count = 3

    # Базовая позиция: относительно реальной позиции карты.
    map_pos = map_item.pagePos()
    map_x = float(map_pos.x())
    map_y = float(map_pos.y())
    map_h = float(map_item.rect().height())
    preferred_x = map_x + 2.0
    preferred_y = map_y + map_h + policy["gutter"]

    base_x = float(x) if x is not None else preferred_x
    if y is not None:
        base_y = float(y)
    else:
        fallback_y = page_height - margin - 14.0
        base_y = preferred_y if preferred_y <= fallback_y else fallback_y

    estimated_width = max(40.0, target_length_mm)
    estimated_height = 12.0
    safe_x, safe_y = place_item_with_policy(
        layout=layout,
        x=base_x,
        y=base_y,
        width=estimated_width,
        height=estimated_height,
        page_width=page_width,
        page_height=page_height,
        zone_x=policy["footer_x"],
        zone_y=policy["footer_y"],
        zone_width=policy["footer_w"],
        zone_height=policy["footer_h"],
        include_maps=True,
        margin=margin,
    )

    return {
        "x": safe_x,
        "y": safe_y,
        "units": units,
        "units_per_segment": units_per_segment,
        "segment_count": segment_count,
        "target_length_mm": target_length_mm,
        "style": "Single Box",
    }
