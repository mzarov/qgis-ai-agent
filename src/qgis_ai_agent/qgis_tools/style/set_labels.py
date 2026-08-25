from typing import Any

from qgis.core import (
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.style.apply import (
    field_names,
    parse_color,
    refresh,
    require_field,
    require_vector_layer,
)
from qgis_ai_agent.qgis_tools.common.values import suggest_fields

DEFAULT_SIZE = 9.0
MIN_SIZE = 3.0
MAX_SIZE = 72.0


class SetLabelsTool(BaseTool):
    name = "set_labels"
    description = (
        "Включить или выключить подписи слоя: каким полем подписывать, каким "
        "размером и цветом. Выключение не трогает остальное оформление."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = ["Поле подписи должно существовать в слое"]
    examples = ["Подпиши города названиями", "Убери подписи с дорог"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "field",
            "type": "string",
            "description": "Поле для подписи. Обязательно, когда подписи включаются.",
            "required": False,
        },
        {
            "name": "enabled",
            "type": "boolean",
            "description": "Включить подписи (по умолчанию true). false — выключить.",
            "required": False,
        },
        {
            "name": "size",
            "type": "number",
            "description": f"Размер шрифта в пунктах, по умолчанию {DEFAULT_SIZE:g}",
            "required": False,
        },
        {
            "name": "color",
            "type": "string",
            "description": "Цвет подписи: #333333 или black",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        if not _is_enabled(params):
            return prepared
        field = (params.get("field") or "").strip()
        if not field:
            raise ValueError(
                f"Чтобы включить подписи, укажите поле. {suggest_fields([], field_names(layer))}"
            )
        prepared["field"] = require_field(layer, field)
        if params.get("size") is not None:
            prepared["size"] = _font_size(params.get("size"))
        if params.get("color"):
            parse_color(params.get("color"), "Цвет подписи")
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not _is_enabled(params):
            return f"Убираю подписи со слоя «{layer_name}»."
        return f"Подписываю «{layer_name}» полем «{params.get('field', '')}»."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        if not _is_enabled(params):
            layer.setLabelsEnabled(False)
            refresh(layer)
            return {"layer": layer.name(), "labels": False}

        settings = QgsPalLayerSettings()
        settings.fieldName = params.get("field") or ""
        settings.isExpression = False
        settings.setFormat(_text_format(params))
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        refresh(layer)
        return {
            "layer": layer.name(),
            "labels": True,
            "field": settings.fieldName,
            "size": _font_size(params.get("size")),
        }


def _text_format(params: dict[str, Any]) -> QgsTextFormat:
    text_format = QgsTextFormat()
    text_format.setSize(_font_size(params.get("size")))
    if params.get("color"):
        text_format.setColor(parse_color(params.get("color"), "Цвет подписи"))
    return text_format


def _is_enabled(params: dict[str, Any]) -> bool:
    value = params.get("enabled")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off")
    return bool(value)


def _font_size(value: Any) -> float:
    if value is None:
        return DEFAULT_SIZE
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Размер шрифта задаётся числом от {MIN_SIZE:g} до {MAX_SIZE:g}.")
    if number < MIN_SIZE or number > MAX_SIZE:
        raise ValueError(f"Размер шрифта должен быть от {MIN_SIZE:g} до {MAX_SIZE:g} пунктов.")
    return number
