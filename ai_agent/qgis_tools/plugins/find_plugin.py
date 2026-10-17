from typing import Any

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.http import get_bytes
from ai_agent.qgis_tools.plugins.discovery import active_plugins
from ai_agent.qgis_tools.plugins.repository import (
    MAX_LIST_BYTES,
    cached_entries,
    installed_plugins,
    parse_repository,
    remember,
    repository_url,
)

MAX_RESULTS = 8
DESCRIPTION_CHARS = 200
MAX_TAGS = 8
# Where a word is found says how much it counts: a name is the plugin, a tag a topic, the text a mention.
NAME_WEIGHT, TAG_WEIGHT, TEXT_WEIGHT = 3, 2, 1


class FindPluginTool(BaseTool):
    name = "find_plugin"
    description = (
        "Search the official QGIS plugin repository (plugins.qgis.org, the list the Plugin Manager "
        "shows for this QGIS version) for plugins that do a task. Each result says whether it is "
        "already installed and active, how often it was downloaded, and whether it is experimental."
    )
    skill = "plugins"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    # The repository list comes from plugins.qgis.org: the user agrees to the request first.
    network_access = True
    constraints = ["Search with the task's words in English: isochrones, routing, segmentation, web map"]
    examples = ["Is there a plugin for isochrones?", "Find a plugin that exports a web map"]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": "Words for the task, e.g. 'isochrones' or 'network analysis'",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Searching the QGIS plugin repository for '{0}'.").format(str(params.get("query") or "").strip())

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        count = len(payload.get("plugins") or [])
        return tr_n("%n plugin(s) found.", count) if count else tr("No plugin found.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        words = [word for word in str(params.get("query") or "").lower().split() if word]
        if not words:
            raise ValueError("Give the task in a few words, e.g. query='isochrones'.")
        entries = cached_entries()
        if entries is None:
            entries = parse_repository(get_bytes(repository_url(), MAX_LIST_BYTES))
            remember(entries)
        installed, active = installed_plugins(), set(active_plugins())
        ranked = sorted(
            ((score(entry, words), entry) for entry in entries if not entry["deprecated"]),
            key=lambda pair: (pair[0], pair[1]["downloads"]),
            reverse=True,
        )
        found = [_shown(entry, installed, active) for points, entry in ranked if points > 0][:MAX_RESULTS]
        return {"plugins": found, "count": len(found), "repository": "plugins.qgis.org"}


def score(entry: dict[str, Any], words: list[str]) -> int:
    name = entry["name"].lower() + " " + entry["key"].lower()
    tags = " ".join(entry["tags"]).lower()
    text = (entry["description"] + " " + entry["about"]).lower()
    points = 0
    for word in words:
        points += NAME_WEIGHT * (word in name) + TAG_WEIGHT * (word in tags) + TEXT_WEIGHT * (word in text)
    return points


def _shown(entry: dict[str, Any], installed: set[str], active: set[str]) -> dict[str, Any]:
    shown: dict[str, Any] = {
        "plugin": entry["key"],
        "name": entry["name"],
        "version": entry["version"],
        "description": entry["description"][:DESCRIPTION_CHARS],
        "tags": entry["tags"][:MAX_TAGS],
        "author": entry["author"],
        "downloads": entry["downloads"],
        "installed": entry["key"] in installed,
        "active": entry["key"] in active,
    }
    if entry["experimental"]:
        shown["experimental"] = True
    return shown
