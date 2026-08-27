from typing import Any

from qgis_ai_agent.plugin import QgisAiAgentPlugin


def classFactory(iface: Any) -> QgisAiAgentPlugin:
    return QgisAiAgentPlugin(iface)
