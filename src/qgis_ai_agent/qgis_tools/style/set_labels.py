from typing import Any

from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.values import suggest_fields
from qgis_ai_agent.qgis_tools.style.apply import (
    field_names,
    parse_color,
    refresh,
    require_field,
    require_vector_layer,
)
from qgis_ai_agent.qgis_tools.style.label_format import (
    DEFAULT_BUFFER_COLOR,
    DEFAULT_BUFFER_SIZE,
    DEFAULT_SIZE,
    buffer_size,
    font_size,
    is_enabled,
    text_format,
    wants_buffer,
)


class SetLabelsTool(BaseTool):
    name = "set_labels"
    description = (
        "Включить или выключить подписи слоя: каким полем подписывать, каким "
        "размером и цветом, нужна ли обводка вокруг текста (ореол, буфер), "
        "чтобы подписи читались поверх пёстрой карты. Остальное оформление не трогает."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = ["Поле подписи должно существовать в слое"]
    examples = [
        "Подпиши города названиями",
        "Убери подписи с дорог",
        "Сделай белую обводку у подписей, чтобы читались",
    ]
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
            "description": "Цвет самого текста подписи: #333333 или black",
            "required": False,
        },
        {
            "name": "buffer_color",
            "type": "string",
            "description": (
                "Цвет обводки вокруг текста (ореол, буфер). Задать — включить "
                "обводку, обычно white."
            ),
            "required": False,
        },
        {
            "name": "buffer_size",
            "type": "number",
            "description": (
                f"Толщина обводки текста в миллиметрах, по умолчанию {DEFAULT_BUFFER_SIZE:g}"
            ),
            "required": False,
        },
        {
            "name": "buffer",
            "type": "boolean",
            "description": "false — убрать обводку текста, оставив подписи на месте",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        if not is_enabled(params):
            return prepared
        field = (params.get("field") or "").strip()
        if not field:
            raise ValueError(
                f"Чтобы включить подписи, укажите поле. {suggest_fields([], field_names(layer))}"
            )
        prepared["field"] = require_field(layer, field)
        if params.get("size") is not None:
            prepared["size"] = font_size(params.get("size"))
        if params.get("color"):
            parse_color(params.get("color"), "Цвет подписи")
        if params.get("buffer_color"):
            parse_color(params.get("buffer_color"), "Цвет обводки текста")
        if params.get("buffer_size") is not None:
            prepared["buffer_size"] = buffer_size(params.get("buffer_size"))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not is_enabled(params):
            return f"Убираю подписи со слоя «{layer_name}»."
        parts = [f"Подписываю «{layer_name}» полем «{params.get('field', '')}»"]
        if params.get("color"):
            parts.append(f"цвет {params['color']}")
        if params.get("size") is not None:
            parts.append(f"размер {params['size']}")
        if wants_buffer(params):
            parts.append(f"обводка текста {params.get('buffer_color') or DEFAULT_BUFFER_COLOR}")
        elif params.get("buffer") is not None:
            parts.append("без обводки текста")
        return ", ".join(parts) + "."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        if not is_enabled(params):
            layer.setLabelsEnabled(False)
            refresh(layer)
            return {"layer": layer.name(), "labels": False}

        settings = QgsPalLayerSettings()
        settings.fieldName = params.get("field") or ""
        settings.isExpression = False
        settings.setFormat(text_format(params))
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        refresh(layer)
        return {
            "layer": layer.name(),
            "labels": True,
            "field": settings.fieldName,
            "size": font_size(params.get("size")),
            "buffer": wants_buffer(params),
        }
