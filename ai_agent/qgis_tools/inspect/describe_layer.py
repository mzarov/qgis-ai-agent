from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layer_meta import describe_source
from ai_agent.qgis_tools.common.layers import (
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
from ai_agent.qgis_tools.common.renderers import style_block

MAX_FIELDS = 60
RASTER_PROPERTIES = (("width", "width"), ("height", "height"), ("band_count", "bandCount"))


class DescribeLayerTool(BaseTool):
    name = "describe_layer"
    description = (
        "Show the details of a layer: attribute fields with their types, extent, "
        "coordinate system and its units, feature count, data source, active filter and a "
        "short styling summary. For a layer in degrees it suggests a metric CRS."
    )
    skill = "inspect"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    constraints = ["A layer with this name must exist in the project"]
    examples = ["Which fields does the 'Cities' layer have?", "What CRS is the roads layer in?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project (see list_layers)",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not layer_name:
            return tr("Reading the layer.")
        return tr("Reading layer '{0}'.").format(layer_name)

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
        result.update(style_block(layer))
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
                f"showing the first {MAX_FIELDS} fields out of {len(described)}; "
                "the rest exist in the layer but are not listed here"
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
