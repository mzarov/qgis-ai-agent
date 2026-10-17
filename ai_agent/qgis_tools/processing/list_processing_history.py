from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsProcessingUtils, QgsProject
from qgis.gui import QgsGui
from qgis.PyQt.QtCore import QDateTime, Qt

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.values import clamp_limit

LOG_TAG = "AI Agent"
HISTORY_PROVIDER = "processing"
DEFAULT_LIMIT = 10
MAX_LIMIT = 30
HISTORY_DAYS = 30
MAX_PARAMETERS = 25
MAX_VALUE_CHARS = 160
MAX_LIST_ITEMS = 10
# Model runs report every child's inputs and results too: noise for picking steps.
MODEL_RESULT_KEYS = frozenset({"CHILD_INPUTS", "CHILD_RESULTS"})
SCOPE_NOTE = (
    "Runs started from Processing dialogs, oldest first. The agent's own run_processing calls are not "
    "recorded here: take those from this conversation."
)
UNAVAILABLE_NOTE = (
    "QGIS's Processing history is not available in this session. Use the run_processing calls of this "
    "conversation, or ask the user which algorithms they ran."
)


class ListProcessingHistoryTool(BaseTool):
    name = "list_processing_history"
    description = (
        "List the user's recent Processing runs from QGIS's own history: when, algorithm id, parameters and "
        "results, oldest first. project_layers names the layers of this project a parameter or result points "
        "at. Use it to turn steps the user ran by hand into a model."
    )
    skill = "processing"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Build a model from the steps I just ran", "Which algorithms did I run today?"]
    params_schema = [
        {
            "name": "limit",
            "type": "integer",
            "description": f"How many of the latest runs to return (default {DEFAULT_LIMIT}, at most {MAX_LIMIT})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the Processing history.")

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        if payload.get("available") is False:
            return tr("History unavailable")
        return tr_n("%n run(s)", len(payload.get("entries") or []))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = clamp_limit(params.get("limit"), DEFAULT_LIMIT, MAX_LIMIT)
        entries = _recent_entries()
        if entries is None:
            return {"available": False, "entries": [], "note": UNAVAILABLE_NOTE}
        entries.sort(key=lambda entry: int(entry.id))
        layers = project_layer_names()
        shown = [history_entry(dict(entry.entry or {}), _when(entry.timestamp), layers) for entry in entries[-limit:]]
        return {"available": True, "total_recent": len(entries), "entries": shown, "note": SCOPE_NOTE}


def history_entry(details: dict[str, Any], when: str, layers: dict[str, str]) -> dict[str, Any]:
    """One run as the model reads it: parameters shortened, project layers named."""
    shaped: dict[str, Any] = {"when": when, "algorithm_id": str(details.get("algorithm_id") or "")}
    parameters = details.get("parameters")
    # The Processing dialog stores asMap(): the values under "inputs", the project's units beside them.
    if isinstance(parameters, dict) and isinstance(parameters.get("inputs"), dict):
        parameters = parameters["inputs"]
    if isinstance(parameters, dict):
        kept = list(parameters.items())[:MAX_PARAMETERS]
        shaped["parameters"] = {str(key): shorten(value) for key, value in kept}
        named = _named_layers(dict(kept), layers)
        if named:
            shaped["project_layers"] = named
    elif details.get("python_command"):
        shaped["python_command"] = shorten(str(details["python_command"]))
    results = details.get("results")
    shaped["finished"] = isinstance(results, dict)
    if isinstance(results, dict):
        kept_results = {str(key): value for key, value in results.items() if key not in MODEL_RESULT_KEYS}
        shaped["results"] = {key: shorten(value) for key, value in kept_results.items()}
        named = _named_layers(kept_results, layers)
        if named:
            shaped["result_layers"] = named
    return shaped


def shorten(value: Any, depth: int = 0) -> Any:
    """A JSON-safe value no longer than a line: long text cut, long lists capped, objects as text."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_VALUE_CHARS else value[: MAX_VALUE_CHARS - 1] + "…"
    if isinstance(value, (list, tuple)) and depth < 2:
        items = [shorten(item, depth + 1) for item in value[:MAX_LIST_ITEMS]]
        return items + ["…"] if len(value) > MAX_LIST_ITEMS else items
    if isinstance(value, dict) and depth < 2:
        return {str(key): shorten(item, depth + 1) for key, item in list(value.items())[:MAX_LIST_ITEMS]}
    return shorten(str(value), depth)


def project_layer_names() -> dict[str, str]:
    """Every way a history entry can point at a layer of the open project — id, source, Processing's string."""
    names: dict[str, str] = {}
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name()
        for identifier in (layer.id(), layer.source(), _processing_identifier(layer)):
            if identifier:
                names.setdefault(str(identifier), name)
    return names


def _named_layers(values: dict[str, Any], layers: dict[str, str]) -> dict[str, str]:
    return {str(key): layers[value] for key, value in values.items() if isinstance(value, str) and value in layers}


def _processing_identifier(layer: Any) -> str:
    try:
        return str(QgsProcessingUtils.layerToStringIdentifier(layer) or "")
    except Exception:
        return ""


def _recent_entries() -> list[Any] | None:
    """Entries of the last HISTORY_DAYS days, or None when this QGIS keeps no history to read."""
    try:
        registry = QgsGui.historyProviderRegistry()
        if registry is None:
            return None
        since = QDateTime.currentDateTime().addDays(-HISTORY_DAYS)
        return list(registry.queryEntries(since, QDateTime(), HISTORY_PROVIDER))
    except Exception as err:
        QgsMessageLog.logMessage(f"Processing history unreadable: {err}", LOG_TAG, Qgis.MessageLevel.Warning)
        return None


def _when(timestamp: Any) -> str:
    try:
        return str(timestamp.toString(Qt.DateFormat.ISODate))
    except Exception:
        return str(timestamp)
