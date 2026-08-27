from typing import Any

from qgis.core import QgsGraduatedSymbolRenderer

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.style.apply import (
    base_symbol,
    refresh,
    require_field,
    require_vector_layer,
    resolve_ramp,
)

MODES = {
    "equal": "EqualInterval",
    "quantile": "Quantile",
    "jenks": "Jenks",
    "pretty": "Pretty",
    "stddev": "StdDev",
}
DEFAULT_MODE = "quantile"
DEFAULT_CLASSES = 5
MIN_CLASSES = 2
MAX_CLASSES = 20
DEFAULT_RAMPS = ("Viridis", "Blues", "Spectral")


class SetGraduatedTool(BaseTool):
    name = "set_graduated"
    description = (
        "Раскрасить слой градациями по числовому полю: разбить значения на классы "
        "и залить их палитрой. Заменяет оформление слоя."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = [
        "Поле должно существовать и содержать числа",
        f"Число классов от {MIN_CLASSES} до {MAX_CLASSES}",
    ]
    examples = ["Раскрась районы по населению", "Градации по площади, 7 классов, Viridis"]
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
            "description": "Числовое поле, по которому строятся градации",
            "required": True,
        },
        {
            "name": "ramp",
            "type": "string",
            "description": (
                "Имя палитры QGIS, например Viridis или Reds. Без неё берётся разумная "
                "по умолчанию; неизвестное имя вернёт список доступных."
            ),
            "required": False,
        },
        {
            "name": "classes",
            "type": "integer",
            "description": f"Сколько классов, по умолчанию {DEFAULT_CLASSES}",
            "required": False,
        },
        {
            "name": "mode",
            "type": "string",
            "enum": sorted(MODES),
            "description": (
                "Способ разбиения: quantile — поровну объектов, equal — равные "
                "интервалы, jenks — естественные границы, pretty — круглые числа, "
                "stddev — по стандартному отклонению."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = require_field(layer, (params.get("field") or "").strip())
        _require_numeric(layer, field)
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["field"] = field
        prepared["classes"] = _class_count(params.get("classes"))
        prepared["mode"] = _mode_name(params.get("mode"))
        resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        classes = params.get("classes") or DEFAULT_CLASSES
        return f"Строю градации «{layer_name}» по «{params.get('field', '')}», классов: {classes}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector_layer(params.get("layer_name") or "")
        field = params.get("field") or ""
        classes = _class_count(params.get("classes"))
        mode = _mode_name(params.get("mode"))
        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            field,
            classes,
            getattr(QgsGraduatedSymbolRenderer, MODES[mode]),
            base_symbol(layer),
            resolve_ramp(params.get("ramp") or "", DEFAULT_RAMPS),
        )
        if renderer is None:
            raise ValueError(
                f"QGIS не смог построить градации по полю «{field}»: возможно, все "
                "значения одинаковы или пусты."
            )
        layer.setRenderer(renderer)
        refresh(layer)
        return {
            "layer": layer.name(),
            "renderer": "graduatedSymbol",
            "class_attribute": field,
            "class_count": len(renderer.ranges()),
            "mode": mode,
        }


def _require_numeric(layer: Any, field: str) -> None:
    index = layer.fields().indexFromName(field)
    if index < 0:
        return
    if not layer.fields().at(index).isNumeric():
        raise ValueError(
            f"Поле «{field}» не числовое, градации по нему не строятся. "
            "Для текстовых значений используйте set_categories."
        )


def _class_count(value: Any) -> int:
    if value is None:
        return DEFAULT_CLASSES
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Число классов задаётся целым числом от {MIN_CLASSES} до {MAX_CLASSES}.")
    if number < MIN_CLASSES or number > MAX_CLASSES:
        raise ValueError(f"Число классов должно быть от {MIN_CLASSES} до {MAX_CLASSES}.")
    return number


def _mode_name(value: Any) -> str:
    name = (str(value or DEFAULT_MODE)).strip().lower()
    if name not in MODES:
        raise ValueError(f"Неизвестный способ разбиения «{value}». Доступны: {', '.join(sorted(MODES))}.")
    return name
