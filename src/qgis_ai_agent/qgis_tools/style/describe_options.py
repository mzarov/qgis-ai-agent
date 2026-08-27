from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.style.label_catalogue import LABELS
from qgis_ai_agent.qgis_tools.style.symbol_catalogue import SYMBOLS

KINDS = {"labels": LABELS, "symbol": SYMBOLS}
USAGE_NOTE = (
    "Свойства передаются одним объектом properties в set_labels или set_symbol. "
    "Указывайте только те, что нужно изменить: остальные останутся по умолчанию."
)


class DescribeStyleOptionsTool(BaseTool):
    name = "describe_style_options"
    description = (
        "Показать, какими свойствами можно управлять у подписей или у символа "
        "слоя: имена, типы, допустимые значения, единицы измерения. Вызвать "
        "перед set_labels или set_symbol, если не уверены в имени свойства."
    )
    skill = "style"
    safety = SAFETY_READ
    constraints = []
    examples = ["Какие настройки подписей доступны?", "Как сдвинуть подписи?"]
    params_schema = [
        {
            "name": "kind",
            "type": "string",
            "enum": sorted(KINDS),
            "description": "labels — свойства подписей, symbol — свойства символа слоя",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        kind = (params.get("kind") or "").strip()
        return f"Смотрю доступные свойства: {kind}." if kind else "Смотрю доступные свойства."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        known = _resolve(params.get("kind"))
        described = known.catalogue()
        return {
            "kind": (params.get("kind") or "").strip().lower(),
            "properties": described,
            "property_count": len(described),
            "usage": USAGE_NOTE,
        }


def _resolve(kind: Any) -> Any:
    name = str(kind or "").strip().lower()
    if name not in KINDS:
        raise ValueError(f"Неизвестный вид «{kind}». Доступны: {', '.join(sorted(KINDS))}.")
    return KINDS[name]
