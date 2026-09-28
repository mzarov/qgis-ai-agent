from contextlib import suppress
from typing import Any

from qgis.core import Qgis, QgsApplication

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool

MAX_PROVIDERS = 20


class GetQgisInfoTool(BaseTool):
    name = "get_qgis_info"
    description = (
        "Show the environment: QGIS version, interface language and the available "
        "processing algorithm providers. Needed to avoid offering what is not installed."
    )
    skill = "inspect"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Which QGIS version do I have?", "Is GRASS available?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the QGIS version and environment.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "qgis_version": self._version(),
            "locale": self._locale(),
            "processing_providers": self._providers(),
        }

    @staticmethod
    def _version() -> str:
        for attribute in ("QGIS_VERSION", "version"):
            with suppress(Exception):
                value = getattr(Qgis, attribute)
                return value() if callable(value) else str(value)
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
            with suppress(Exception):
                names.append(provider.id())
        return names
