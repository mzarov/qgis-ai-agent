from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.plugins.discovery import (
    ABOUT_CHARS,
    algorithms,
    menu_commands,
    metadata,
    providers,
    require_plugin,
)

MAX_ALGORITHMS = 60


class DescribePluginTool(BaseTool):
    name = "describe_plugin"
    description = (
        "Show what one installed plugin offers: its description, its Processing algorithms "
        "(run them with the processing skill) and its menu commands (run_plugin_command)."
    )
    skill = "plugins"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["What can the QuickMapServices plugin do?"]
    params_schema = [
        {"name": "plugin", "type": "string", "description": "Plugin package or display name from list_plugins"},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        return {**params, "plugin": require_plugin(params.get("plugin"))}

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading what plugin '{0}' offers.").format(str(params.get("plugin") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        plugin = require_plugin(params.get("plugin"))
        found = []
        for provider in providers(plugin):
            found.extend(algorithms(provider))
        result: dict[str, Any] = {
            "plugin": plugin,
            "name": metadata(plugin, "name") or plugin,
            "about": (metadata(plugin, "about") or metadata(plugin, "description"))[:ABOUT_CHARS],
            "processing_algorithms": found[:MAX_ALGORITHMS],
            "menu_commands": sorted(menu_commands(plugin)),
        }
        if len(found) > MAX_ALGORITHMS:
            result["algorithms_note"] = f"{len(found)} algorithms; search_processing finds the rest."
        if not found and not result["menu_commands"]:
            result["note"] = "This plugin exposes no algorithm or menu command the agent can reach."
        return result
