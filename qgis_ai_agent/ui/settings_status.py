from typing import Any

from qgis_ai_agent.core.llm.client import resolve_endpoint
from qgis_ai_agent.ui import settings_fields as fields
from qgis_ai_agent.ui import style


class SettingsStatusMixin:
    def _valid_url(self, url: str) -> bool:
        try:
            resolve_endpoint(url)
        except ValueError as error:
            self._show(str(error), style.danger(self.palette()))
            return False
        return True

    def _show(self, message: str, colour: Any) -> None:
        fields.paint_status(self._status, message, colour)
