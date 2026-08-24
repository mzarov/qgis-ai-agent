from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.utils import (
    crs_authid,
    crs_is_geographic,
    crs_units,
    extent_dict,
    find_layer_by_name,
    geometry_type_name,
    layer_kind,
)

# Ограничение на число полей в ответе, чтобы не раздувать контекст модели.
MAX_FIELDS = 60


class DescribeLayerTool(BaseTool):
    """Подробное описание одного слоя: поля, охват, система координат."""
    name = "describe_layer"
    description = (
        "Показать подробности слоя: список полей атрибутов с типами, охват (extent), "
        "систему координат, число объектов. Нужен перед стилизацией и анализом."
    )
    skill = "inspect"
    safety = SAFETY_READ
    capabilities = ["project:layer:describe"]
    examples = ["Какие поля в слое «Населённые пункты»?", "Покажи атрибуты слоя дорог"]
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте (см. list_layers)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага чтения деталей слоя."""
        layer_name = (params.get("layer_name") or "").strip()
        return f"Смотрю слой «{layer_name}»." if layer_name else "Смотрю слой."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        kind = layer_kind(layer)
        result: dict[str, Any] = {
            "name": (layer.name() or "").strip(),
            "kind": kind,
            "crs": crs_authid(layer),
            "crs_is_geographic": crs_is_geographic(layer),
            "crs_units": crs_units(layer),
            "extent": extent_dict(self._safe_extent(layer)),
        }
        if isinstance(layer, QgsVectorLayer):
            result["geometry"] = geometry_type_name(layer)
            result["feature_count"] = self._safe_feature_count(layer)
            result["fields"] = self._describe_fields(layer)
        elif isinstance(layer, QgsRasterLayer):
            result.update(self._describe_raster(layer))
        return result

    @staticmethod
    def _safe_extent(layer):
        try:
            return layer.extent()
        except Exception:
            return None

    @staticmethod
    def _safe_feature_count(layer: QgsVectorLayer) -> int | None:
        try:
            return int(layer.featureCount())
        except Exception:
            return None

    @staticmethod
    def _describe_fields(layer: QgsVectorLayer) -> list[dict[str, Any]]:
        """Собирает список полей атрибутов с типами."""
        fields: list[dict[str, Any]] = []
        try:
            for field in layer.fields():
                fields.append(
                    {
                        "name": field.name(),
                        "type": field.typeName() or str(field.type()),
                    }
                )
                if len(fields) >= MAX_FIELDS:
                    break
        except Exception:
            pass
        return fields

    @staticmethod
    def _describe_raster(layer: QgsRasterLayer) -> dict[str, Any]:
        """Собирает базовые характеристики растрового слоя."""
        info: dict[str, Any] = {}
        for key, getter in (
            ("width", "width"),
            ("height", "height"),
            ("band_count", "bandCount"),
        ):
            try:
                info[key] = int(getattr(layer, getter)())
            except Exception:
                continue
        return info
