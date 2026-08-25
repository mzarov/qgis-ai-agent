from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.style.label_catalogue import catalogue

USAGE_NOTE = (
    "Все свойства передаются в set_labels одним объектом properties. "
    "Указывайте только те, что нужно изменить: остальные останутся по умолчанию."
)


class DescribeLabelOptionsTool(BaseTool):
    name = "describe_label_options"
    description = (
        "Показать, какими свойствами можно управлять у подписей: имена, типы, "
        "допустимые значения, единицы измерения. Вызвать перед set_labels, если "
        "не уверены в имени свойства."
    )
    skill = "style"
    safety = SAFETY_READ
    constraints = []
    examples = ["Какие настройки подписей доступны?", "Как сдвинуть подписи?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return "Смотрю доступные настройки подписей."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        described = catalogue()
        return {"properties": described, "property_count": len(described), "usage": USAGE_NOTE}
