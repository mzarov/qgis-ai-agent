from typing import Any

from qgis.core import QgsVectorLayerSimpleLabeling

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.values import suggest_fields
from qgis_ai_agent.qgis_tools.style.apply import (
    field_names,
    refresh,
    require_field,
    require_vector_layer,
)
from qgis_ai_agent.qgis_tools.common.properties import properties_of, shown
from qgis_ai_agent.qgis_tools.style.label_build import build_settings, wants
from qgis_ai_agent.qgis_tools.style.label_catalogue import LABELS
from qgis_ai_agent.qgis_tools.common.properties import as_bool


class SetLabelsTool(BaseTool):
    name = "set_labels"
    description = (
        "Настроить подписи слоя одним вызовом: поле, шрифт, начертание, размер, "
        "цвет, обводку текста, сдвиг, поворот, размещение, тень, подложку. "
        "Полный список свойств отдаёт describe_style_options. Остальное "
        "оформление слоя не трогает."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "Поле подписи должно существовать в слое",
        "Все свойства идут одним вызовом, а не несколькими",
    ]
    examples = [
        "Подпиши города названиями",
        "Сделай подписи жирными с белой обводкой",
        "Сдвинь подписи на 3 мм вверх",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "properties",
            "type": "object",
            "description": (
                "Свойства подписи парами ключ-значение, например "
                '{"field": "name", "bold": true, "buffer_color": "white", '
                '"offset_y": -3}. Имена и допустимые значения — '
                'describe_style_options с kind="labels". Незнакомый ключ вернёт подсказку.'
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = LABELS.coerce_all(properties_of(params, LABELS.subject))
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["properties"] = properties
        if not _is_enabled(properties):
            return prepared
        field = str(properties.get("field") or "").strip()
        if not field:
            raise ValueError(
                "Чтобы включить подписи, укажите свойство field. "
                f"{suggest_fields([], field_names(layer))}"
            )
        properties["field"] = require_field(layer, field)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        try:
            properties = properties_of(params, LABELS.subject)
        except ValueError:
            return f"Настраиваю подписи «{layer_name}»."
        if not _is_enabled(properties):
            return f"Убираю подписи со слоя «{layer_name}»."
        return f"Настраиваю подписи «{layer_name}»: {shown(properties, LABELS)}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        properties = LABELS.coerce_all(properties_of(params, LABELS.subject))
        if not _is_enabled(properties):
            layer.setLabelsEnabled(False)
            refresh(layer)
            return {"layer": layer.name(), "labels": False}

        settings = build_settings(properties)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        refresh(layer)
        return {
            "layer": layer.name(),
            "labels": True,
            "field": settings.fieldName,
            "applied": sorted(key for key in properties if key != "enabled"),
            "buffer": wants(properties, "buffer"),
        }


def _is_enabled(properties: dict[str, Any]) -> bool:
    value = properties.get("enabled")
    return True if value is None else as_bool(value)
