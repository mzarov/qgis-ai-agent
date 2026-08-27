import os
from typing import Any

from qgis_ai_agent import i18n

i18n.install(os.path.dirname(os.path.abspath(__file__)))

from qgis_ai_agent.plugin import QgisAiAgentPlugin


def classFactory(iface: Any) -> QgisAiAgentPlugin:
    return QgisAiAgentPlugin(iface)
