from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QTimer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.plugins.discovery import menu_commands, metadata, require_plugin

LOG_TAG = "AI Agent"
STARTED_NOTE = (
    "The command was started. Plugins usually open their own window: the user works with it "
    "there, and you cannot see or drive that window. Ask the user what they did if you need it."
)


class RunPluginCommandTool(BaseTool):
    name = "run_plugin_command"
    description = (
        "Start one menu command of another installed plugin, exactly as the user would click "
        "it. The plugin's own code runs, usually opening its window for the user."
    )
    skill = "plugins"
    # Another plugin's code: nothing here can tell what it changes, sends or deletes.
    safety = SAFETY_DESTRUCTIVE
    egress = EGRESS_METADATA
    external_effect = True
    network_access = False
    constraints = ["command is a path exactly as describe_plugin lists it"]
    examples = ["Open the QuickMapServices settings", "Start the qgis2web export"]
    params_schema = [
        {"name": "plugin", "type": "string", "description": "Plugin package or display name"},
        {"name": "command", "type": "string", "description": "Menu command path from describe_plugin"},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        plugin = require_plugin(params.get("plugin"))
        _command(plugin, params.get("command"))
        return {**params, "plugin": plugin}

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Running a command of plugin '{0}': {1}").format(
            str(params.get("plugin") or "").strip(), str(params.get("command") or "").strip()
        )

    def detail_call(self, params: dict[str, Any]) -> str:
        plugin = str(params.get("plugin") or "").strip()
        return tr(
            "This runs code of the plugin '{0}', not of AI Agent. It may change or delete data, "
            "contact the internet or open its own windows, and undo cannot reverse what it does."
        ).format(metadata(plugin, "name") or plugin)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        plugin = require_plugin(params.get("plugin"))
        path, action = _command(plugin, params.get("command"))
        # Started after this apply step returns: a plugin dialog that runs its own event loop
        # must not block the batch halfway.
        QTimer.singleShot(0, action.trigger)
        QgsMessageLog.logMessage(f"Started plugin command {path}.", LOG_TAG, Qgis.MessageLevel.Info)
        return {"started": path, "note": STARTED_NOTE}


def _command(plugin: str, raw: Any) -> tuple[str, Any]:
    commands = menu_commands(plugin)
    wanted = str(raw or "").strip()
    if wanted in commands:
        return wanted, commands[wanted]
    tail = [path for path in commands if path.lower().endswith(wanted.lower())] if wanted else []
    if len(tail) == 1:
        return tail[0], commands[tail[0]]
    listed = "; ".join(sorted(commands)) or "none"
    raise ValueError(f"Plugin '{plugin}' has no command '{wanted}'. Its commands: {listed}.")
