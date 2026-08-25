from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name
from qgis_ai_agent.qgis_tools.style.apply import clamp_opacity, refresh

PERCENT_THRESHOLD = 1.0
PERCENT_MAX = 100.0


class SetOpacityTool(BaseTool):
    name = "set_opacity"
    description = (
        "Задать прозрачность слоя. Работает и для векторных, и для растровых слоёв, "
        "остальное оформление не трогает."
    )
    skill = "style"
    safety = SAFETY_WRITE
    constraints = ["Слой с указанным именем должен существовать в проекте"]
    examples = ["Сделай подложку полупрозрачной", "Верни слою полную непрозрачность"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "opacity",
            "type": "number",
            "description": (
                "Непрозрачность от 0 до 1, где 1 — полностью непрозрачный. "
                "Значения больше 1 понимаются как проценты."
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["opacity"] = _as_fraction(params.get("opacity"))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip() or "слою"
        try:
            percent = f"{_as_fraction(params.get('opacity')) * PERCENT_MAX:.0f}%"
        except ValueError:
            percent = "заданную величину"
        return f"Ставлю «{layer_name}» непрозрачность {percent}."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        opacity = _as_fraction(params.get("opacity"))
        layer.setOpacity(opacity)
        refresh(layer)
        return {"layer": layer.name(), "opacity": opacity}


def _as_fraction(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Непрозрачность задаётся числом от 0 до 1, например 0.6.")
    if number > PERCENT_THRESHOLD:
        number = number / PERCENT_MAX
    return clamp_opacity(number)
