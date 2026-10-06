from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.plugins.discovery import active_plugins, menu_commands, metadata, providers

DESCRIPTION_CHARS = 160


class ListPluginsTool(BaseTool):
    name = "list_plugins"
    description = (
        "List the other QGIS plugins that are installed and active: what each does, the "
        "Processing provider it adds and how many menu commands it has."
    )
    skill = "plugins"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Which plugins do I have?", "Is there a plugin for segmentation installed?"]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "Words to filter by name or description, e.g. 'segmentation' or 'web map'",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Listing the installed plugins.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        words = [word for word in str(params.get("query") or "").lower().split() if word]
        listed = []
        for plugin in active_plugins():
            entry = _entry(plugin)
            text = " ".join(str(value) for value in entry.values()).lower()
            if not words or any(word in text for word in words):
                listed.append(entry)
        return {"plugins": listed, "count": len(listed)}


def _entry(plugin: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "plugin": plugin,
        "name": metadata(plugin, "name") or plugin,
        "version": metadata(plugin, "version"),
        "description": metadata(plugin, "description")[:DESCRIPTION_CHARS],
    }
    provider_ids = [provider.id() for provider in providers(plugin)]
    if provider_ids:
        entry["processing_providers"] = provider_ids
    commands = len(menu_commands(plugin))
    if commands:
        entry["menu_commands"] = commands
    return entry
