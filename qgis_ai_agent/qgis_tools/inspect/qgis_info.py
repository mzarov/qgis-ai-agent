from typing import Any

from qgis.core import Qgis, QgsApplication

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool

MAX_PROVIDERS = 20


class GetQgisInfoTool(BaseTool):
    name = "get_qgis_info"
    description = (
        "Показать окружение: версию QGIS, язык интерфейса и доступные провайдеры "
        "алгоритмов обработки. Нужен, чтобы не предлагать недоступное."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["Какая у меня версия QGIS?", "Доступен ли GRASS?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return "Смотрю версию и окружение QGIS."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "qgis_version": self._version(),
            "locale": self._locale(),
            "processing_providers": self._providers(),
        }

    @staticmethod
    def _version() -> str:
        for attribute in ("QGIS_VERSION", "version"):
            try:
                value = getattr(Qgis, attribute)
                return value() if callable(value) else str(value)
            except Exception:
                continue
        return ""

    @staticmethod
    def _locale() -> str:
        try:
            return QgsApplication.locale() or ""
        except Exception:
            return ""

    @staticmethod
    def _providers() -> list[str]:
        try:
            providers = QgsApplication.processingRegistry().providers()
        except Exception:
            return []
        names = []
        for provider in list(providers)[:MAX_PROVIDERS]:
            try:
                names.append(provider.id())
            except Exception:
                continue
        return names
