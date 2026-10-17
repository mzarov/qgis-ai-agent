from typing import Any
from urllib.parse import urlparse

from qgis.core import Qgis, QgsMessageLog

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.common.background import Background, InTask
from ai_agent.qgis_tools.common.http import get_bytes
from ai_agent.qgis_tools.plugins.discovery import active_plugins
from ai_agent.qgis_tools.plugins.repository import (
    MAX_ZIP_BYTES,
    cached_entries,
    enable,
    find_entry,
    installed_plugins,
    plugins_folder,
    unpacked,
)

LOG_TAG = "AI Agent"
# Only the official repository's own downloads: a list entry pointing elsewhere is not followed.
REPOSITORY_HOST = "plugins.qgis.org"
FIND_FIRST = "Find the plugin with find_plugin first; install takes the plugin key it returns."
INSTALLED_NOTE = (
    "The plugin is installed and active. See what it offers with describe_plugin and use its "
    "Processing algorithms through the processing skill."
)


class InstallPluginTool(BaseTool):
    name = "install_plugin"
    description = (
        "Install a plugin from the official QGIS plugin repository and start it, as the Plugin "
        "Manager does; a plugin that is installed but switched off is switched on instead. "
        "Take the plugin key from find_plugin. The user confirms every installation."
    )
    skill = "plugins"
    # Someone else's code, run with the user's rights: nothing here can tell what it changes or sends.
    safety = SAFETY_DESTRUCTIVE
    egress = EGRESS_METADATA
    external_effect = True
    network_access = True
    constraints = [
        "plugin is a key from find_plugin in this conversation",
        "Install only what the task needs and the user agreed to",
    ]
    examples = ["Install ORS Tools", "Turn on the QuickMapServices plugin"]
    params_schema = [
        {"name": "plugin", "type": "string", "description": "Plugin key or name from find_plugin", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        entries = cached_entries()
        if entries is None:
            raise ValueError(FIND_FIRST)
        entry = find_entry(entries, str(params.get("plugin") or ""))
        if entry is None:
            raise ValueError(f"No plugin '{params.get('plugin')}' in the repository list. {FIND_FIRST}")
        if entry["deprecated"]:
            raise ValueError(f"'{entry['name']}' is deprecated in the repository; look for another plugin.")
        if entry["key"] in active_plugins():
            raise ValueError(f"'{entry['name']}' is already installed and active; see describe_plugin.")
        link = urlparse(entry["download_url"])
        if link.scheme != "https" or link.hostname != REPOSITORY_HOST:
            raise ValueError(f"'{entry['name']}' is not downloaded from {REPOSITORY_HOST}; it is not installed.")
        return {
            **params,
            "plugin": entry["key"],
            "name": entry["name"],
            "version": entry["version"],
            "author": entry["author"],
            "downloads": entry["downloads"],
            "experimental": entry["experimental"],
            "download_url": entry["download_url"],
            "enable_only": entry["key"] in installed_plugins(),
        }

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("name") or params.get("plugin") or "").strip()
        if params.get("enable_only"):
            return tr("Switching on the installed plugin '{0}'.").format(name)
        return tr("Installing the plugin '{0}' {1} from the QGIS plugin repository.").format(
            name, str(params.get("version") or "")
        )

    def detail_call(self, params: dict[str, Any]) -> str:
        lines = [
            tr("Plugin: {0} {1}").format(str(params.get("name") or ""), str(params.get("version") or "")),
            tr("Author: {0}").format(str(params.get("author") or "")),
            tr("Downloads: {0}").format(params.get("downloads") or 0),
        ]
        if params.get("experimental"):
            lines.append(tr("The author marks this version as experimental."))
        lines.append(
            tr(
                "This installs code that is not part of AI Agent and runs it inside QGIS with your rights. "
                "It may change data or contact the internet, and undo cannot remove it: uninstall it in "
                "Plugins → Manage and Install Plugins."
            )
        )
        return "\n".join(lines)

    def start(self, params: dict[str, Any]) -> Background | None:
        """The download off the main thread; unpacking and starting the plugin happen on it afterwards."""
        if params.get("enable_only"):
            return None
        url = str(params.get("download_url") or "")
        return InTask(
            self.summarize_call(params),
            lambda feedback: get_bytes(url, MAX_ZIP_BYTES, feedback),
            lambda archive: _installed(params, archive),
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("enable_only"):
            enable(str(params.get("plugin") or ""))
            return {"enabled": params.get("plugin"), "note": INSTALLED_NOTE}
        return _installed(params, get_bytes(str(params.get("download_url") or ""), MAX_ZIP_BYTES))

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        key = str(payload.get("installed") or payload.get("enabled") or "")
        return bool(key) and key in active_plugins()


def _installed(params: dict[str, Any], archive: bytes) -> dict[str, Any]:
    key = unpacked(archive, plugins_folder())
    enable(key)
    QgsMessageLog.logMessage(
        f"Installed plugin {key} {params.get('version')} from the QGIS plugin repository.",
        LOG_TAG,
        Qgis.MessageLevel.Info,
    )
    return {"installed": key, "version": params.get("version"), "note": INSTALLED_NOTE}
