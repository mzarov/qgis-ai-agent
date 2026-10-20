import re
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
NAME_WEIGHT, TAG_WEIGHT, TEXT_WEIGHT = 3, 2, 1
PHRASE_WEIGHT = 5
MIN_VARIANT = 3
VERSION_TAIL = re.compile(r"(?<=[a-z])\d+$")
NOT_FOUND_NOTE = (
    "Nothing matched '{query}' among the {listed} plugins listed for this QGIS version. That says nothing "
    "about why: do not tell the user a reason you have not read. Try the task in other words (network "
    "analysis, isochrones) or a shorter name, then say plainly that no plugin was found."
)


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
        result: dict[str, Any] = {
            "plugins": found,
            "count": len(found),
            "listed": len(entries),
            "repository": "plugins.qgis.org",
        }
        if not found:
            result["note"] = NOT_FOUND_NOTE.format(query=" ".join(words), listed=len(entries))
        return result


def score(entry: dict[str, Any], words: list[str]) -> int:
    name = entry["name"].lower() + " " + entry["key"].lower()
    tags = " ".join(entry["tags"]).lower()
    text = (entry["description"] + " " + entry["about"]).lower()
    points = 0
    for word in words:
        points += max(
            NAME_WEIGHT * _has(variant, name) + TAG_WEIGHT * _has(variant, tags) + TEXT_WEIGHT * _has(variant, text)
            for variant in variants(word)
        )
    phrase = " ".join(words)
    if len(words) > 1 and (phrase in tags or phrase in text):
        points += PHRASE_WEIGHT
    return points


def variants(word: str) -> set[str]:
    found = {word, VERSION_TAIL.sub("", word)}
    for ending in ("es", "s"):
        if word.endswith(ending):
            found.add(word[: -len(ending)])
    return {variant for variant in found if len(variant) >= MIN_VARIANT} or {word}


def _has(variant: str, text: str) -> bool:
    if len(variant) >= MIN_VARIANT:
        return variant in text
    return re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", text) is not None


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
