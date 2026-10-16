from ai_agent.qgis_tools.plugins.describe_plugin import DescribePluginTool
from ai_agent.qgis_tools.plugins.find_plugin import FindPluginTool
from ai_agent.qgis_tools.plugins.install_plugin import InstallPluginTool
from ai_agent.qgis_tools.plugins.list_plugins import ListPluginsTool
from ai_agent.qgis_tools.plugins.run_plugin_command import RunPluginCommandTool

PLUGINS_TOOLS = [
    ListPluginsTool(),
    DescribePluginTool(),
    RunPluginCommandTool(),
    FindPluginTool(),
    InstallPluginTool(),
]
