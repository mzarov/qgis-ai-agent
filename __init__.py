import os
import sys

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_src_pkg = os.path.join(_plugin_dir, "src", "qgis_ai_agent")
if _src_pkg not in __path__:
    __path__.insert(0, _src_pkg)

from qgis_ai_agent.core.plugin import QgisAiAgentPlugin


def classFactory(iface):
    return QgisAiAgentPlugin(iface)
