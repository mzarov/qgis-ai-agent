from typing import Any

from qgis.core import QgsLayoutItemScaleBar, QgsLayoutPoint

from qgis_ai_agent.qgis_tools.base import BaseTool
from qgis_ai_agent.qgis_tools.layout.layout_composer import build_layout_policy
from qgis_ai_agent.qgis_tools.layout.scalebar_composer import compose_scalebar_params
from qgis_ai_agent.qgis_tools.layout.utils import (
    LAYOUT_UNIT_MM,
    clamp_to_page_bounds,
    get_first_map_item,
    get_layout,
    get_page_size_mm,
    place_item_with_policy,
)


class AddScaleBarTool(BaseTool):
    """Добавление масштабной линейки на макет, привязанной к карте."""
    name = "add_scale_bar"
    description = (
        "Добавить масштабную линейку, привязанную к карте. "
        "По умолчанию автоматически подбирает информативные деления и длину."
    )
    capabilities = ["layout:scalebar:add"]
    examples = ["Добавь масштабную линейку внизу карты"]
    constraints = [
        "В макете должна быть карта, иначе tool возвращает ошибку",
        "Если параметры делений не заданы явно, tool выбирает их автоматически",
    ]
    params_schema = [
        {"name": "layout_name", "type": "string", "description": "Имя макета", "required": True},
        {"name": "x", "type": "number", "description": "X позиции линейки в мм", "required": False},
        {"name": "y", "type": "number", "description": "Y позиции линейки в мм", "required": False},
        {"name": "style", "type": "string", "description": "Стиль: Single Box, Double Box, Numeric, Line Ticks Up, Line Ticks Down, Line Ticks Middle, Stepped Line, Hollow", "required": False},
        {"name": "units", "type": "string", "description": "Единицы: m, km, ft, mi, nautical miles", "required": False},
        {"name": "units_per_segment", "type": "number", "description": "Значение на деление (опционально)", "required": False},
        {"name": "segment_count", "type": "number", "description": "Количество делений справа (опционально)", "required": False},
    ]

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = params.get("layout_name") or "Макет ИИ"
        x_raw = params.get("x")
        y_raw = params.get("y")
        x = float(x_raw) if x_raw is not None else None
        y = float(y_raw) if y_raw is not None else None
        style = (params.get("style") or "").strip()
        units = (params.get("units") or "").strip()
        units_per_segment = params.get("units_per_segment")
        segment_count = params.get("segment_count")

        layout = get_layout(layout_name)
        map_item = get_first_map_item(layout)
        if not map_item:
            raise ValueError("На макете нет карты для привязки масштабной линейки.")

        auto_cfg = compose_scalebar_params(
            layout=layout,
            map_item=map_item,
            x=x,
            y=y,
            preferred_units=units or None,
        )
        final_x = float(auto_cfg["x"]) if x is None else x
        final_y = float(auto_cfg["y"]) if y is None else y
        final_style = style or str(auto_cfg["style"])
        final_units = units or str(auto_cfg["units"])
        final_units_per_segment = (
            float(units_per_segment)
            if units_per_segment is not None
            else float(auto_cfg["units_per_segment"])
        )
        final_segment_count = (
            int(segment_count) if segment_count is not None else int(auto_cfg["segment_count"])
        )
        final_segment_count = max(2, final_segment_count)

        scale_bar = QgsLayoutItemScaleBar(layout)
        scale_bar.setStyle(final_style)
        scale_bar.setLinkedMap(map_item)
        layout.addLayoutItem(scale_bar)
        # Если модель передала "m" для очень крупного масштаба, делаем подписи читаемыми.
        if units_per_segment is None and final_units.lower() in ("m", "meters", "метры") and final_units_per_segment >= 50000:
            final_units = "km"
            final_units_per_segment = max(1.0, final_units_per_segment / 1000.0)

        unit_enum = self._units_enum(final_units) if final_units else None
        if unit_enum is not None:
            scale_bar.setUnits(unit_enum)

        # configure -> measure: сначала полностью конфигурируем и измеряем фактический размер.
        self._apply_segment_config(scale_bar, final_units_per_segment, final_segment_count)
        scale_bar.applyDefaultSize()
        scale_bar.update()

        page_width, page_height = get_page_size_mm(layout)
        policy = build_layout_policy(layout)
        max_width = max(40.0, page_width - policy["margin"] * 2)

        # Безопасно уменьшаем количество сегментов, если линейка шире safe-area.
        adaptive_segments = final_segment_count
        adaptive_units_per_segment = float(final_units_per_segment)
        bar_width, _ = self._actual_size_mm(scale_bar)
        while bar_width > max_width and adaptive_segments > 2:
            adaptive_segments -= 1
            self._apply_segment_config(scale_bar, adaptive_units_per_segment, adaptive_segments)
            scale_bar.applyDefaultSize()
            scale_bar.update()
            bar_width, _ = self._actual_size_mm(scale_bar)

        # Если даже на минимальном количестве сегментов ширина избыточна,
        # уменьшаем units_per_segment до тех пор, пока линейка не войдёт в safe-area.
        reduce_guard = 0
        while bar_width > max_width and reduce_guard < 6:
            adaptive_units_per_segment = max(1.0, adaptive_units_per_segment * 0.7)
            self._apply_segment_config(scale_bar, adaptive_units_per_segment, adaptive_segments)
            scale_bar.applyDefaultSize()
            scale_bar.update()
            bar_width, _ = self._actual_size_mm(scale_bar)
            reduce_guard += 1

        bar_width, bar_height = self._actual_size_mm(scale_bar)

        # place: размещаем после фактического измерения, затем делаем post-clamp.
        safe_x, safe_y = place_item_with_policy(
            layout=layout,
            x=final_x,
            y=final_y,
            width=bar_width,
            height=bar_height,
            page_width=page_width,
            page_height=page_height,
            zone_x=policy["footer_x"],
            zone_y=policy["footer_y"],
            zone_width=policy["footer_w"],
            zone_height=policy["footer_h"],
            include_maps=True,
            margin=policy["margin"],
        )
        scale_bar.attemptMove(QgsLayoutPoint(safe_x, safe_y, LAYOUT_UNIT_MM))
        # Post-clamp: финальная коррекция после attemptMove.
        post_pos = scale_bar.pagePos()
        post_x, post_y = clamp_to_page_bounds(
            float(post_pos.x()),
            float(post_pos.y()),
            bar_width,
            bar_height,
            page_width,
            page_height,
            margin=policy["margin"],
        )
        if abs(float(post_pos.x()) - post_x) > 0.01 or abs(float(post_pos.y()) - post_y) > 0.01:
            scale_bar.attemptMove(QgsLayoutPoint(post_x, post_y, LAYOUT_UNIT_MM))
        return {
            "layout_name": layout_name,
            "segment_count": adaptive_segments,
            "units_per_segment": adaptive_units_per_segment,
        }

    @staticmethod
    def _actual_size_mm(scale_bar: QgsLayoutItemScaleBar) -> tuple[float, float]:
        """Возвращает фактический размер линейки после конфигурации."""
        rect = scale_bar.rect()
        return float(rect.width()), float(rect.height())

    @staticmethod
    def _apply_segment_config(
        scale_bar: QgsLayoutItemScaleBar,
        units_per_segment: float,
        segment_count: int,
    ) -> None:
        if hasattr(scale_bar, "setUnitsPerSegment"):
            scale_bar.setUnitsPerSegment(units_per_segment)
        if hasattr(scale_bar, "setNumberOfSegments"):
            scale_bar.setNumberOfSegments(segment_count)
        elif hasattr(scale_bar, "setNumberOfSegmentsRight"):
            scale_bar.setNumberOfSegmentsRight(segment_count)
            if hasattr(scale_bar, "setNumberOfSegmentsLeft"):
                scale_bar.setNumberOfSegmentsLeft(0)

    @staticmethod
    def _units_enum(units: str):
        from qgis.core import Qgis
        u = units.lower()
        du = getattr(Qgis, "DistanceUnit", None)
        if du is None:
            return None
        if u in ("m", "meters", "метры"):
            return getattr(du, "Meters", None)
        if u in ("km", "kilometers", "километры"):
            return getattr(du, "Kilometers", None)
        if u in ("ft", "feet", "футы"):
            return getattr(du, "Feet", None)
        if u in ("mi", "miles", "мили"):
            return getattr(du, "Miles", None)
        if u in ("nautical", "nm", "морские"):
            return getattr(du, "NauticalMiles", None)
        return getattr(du, "Meters", None)
