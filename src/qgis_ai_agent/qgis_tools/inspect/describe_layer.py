from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.layer_meta import describe_source
from qgis_ai_agent.qgis_tools.inspect.utils import (
    crs_authid,
    crs_is_geographic,
    crs_units,
    extent_dict,
    find_layer_by_name,
    geometry_type_name,
    layer_kind,
    safe_extent,
    safe_feature_count,
    suggest_metric_crs,
)
from qgis_ai_agent.qgis_tools.style.renderers import renderer_summary

MAX_FIELDS = 60
RASTER_PROPERTIES = (("width", "width"), ("height", "height"), ("band_count", "bandCount"))


class DescribeLayerTool(BaseTool):
    name = "describe_layer"
    description = (
        "Показать подробности слоя: поля атрибутов с типами, охват, систему координат "
        "и её единицы, число объектов, источник данных, активный фильтр и краткую "
        "сводку оформления. Для слоя в градусах подсказывает метрическую CRS."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    examples = ["Какие поля в слое «Города»?", "В какой проекции слой дорог?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте (см. list_layers)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Смотрю слой «{layer_name}»." if layer_name else "Смотрю слой."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        result: dict[str, Any] = {
            "name": (layer.name() or "").strip(),
            "kind": layer_kind(layer),
            "crs": crs_authid(layer),
            "crs_is_geographic": crs_is_geographic(layer),
            "crs_units": crs_units(layer),
            "extent": extent_dict(safe_extent(layer)),
        }
        result.update(describe_source(layer))
        style = renderer_summary(layer)
        if style:
            result["style_summary"] = style
        if crs_is_geographic(layer):
            result["suggested_metric_crs"] = suggest_metric_crs(layer)
        if isinstance(layer, QgsVectorLayer):
            result["geometry"] = geometry_type_name(layer)
            result["feature_count"] = safe_feature_count(layer)
            result.update(self._fields_block(layer))
        elif isinstance(layer, QgsRasterLayer):
            result.update(self._describe_raster(layer))
        return result

    @classmethod
    def _fields_block(cls, layer: QgsVectorLayer) -> dict[str, Any]:
        described = cls._describe_fields(layer)
        block: dict[str, Any] = {"fields": described[:MAX_FIELDS], "field_count": len(described)}
        if len(described) > MAX_FIELDS:
            block["fields_note"] = (
                f"показаны первые {MAX_FIELDS} полей из {len(described)}; "
                "остальные есть в слое, но здесь не перечислены"
            )
        return block

    @staticmethod
    def _describe_fields(layer: QgsVectorLayer) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        try:
            for field in layer.fields():
                fields.append({"name": field.name(), "type": field.typeName() or str(field.type())})
        except Exception:
            pass
        return fields

    @staticmethod
    def _describe_raster(layer: QgsRasterLayer) -> dict[str, Any]:
        info: dict[str, Any] = {}
        for key, getter in RASTER_PROPERTIES:
            try:
                info[key] = int(getattr(layer, getter)())
            except Exception:
                continue
        return info
