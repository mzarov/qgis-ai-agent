import json
from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsProcessingUtils, QgsProject
from qgis.gui import QgsGui
from qgis.PyQt.QtCore import QDateTime, Qt

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layer_meta import MASKED_VALUE, is_secret_name, sanitize_source
from ai_agent.qgis_tools.common.values import clamp_limit

LOG_TAG = "AI Agent"
HISTORY_PROVIDER = "processing"
DEFAULT_LIMIT = 10
MAX_LIMIT = 30
HISTORY_DAYS = 30
MAX_PARAMETERS = 25
MAX_VALUE_CHARS = 160
MAX_LIST_ITEMS = 10
MAX_DEPTH = 2
ELIDED = "…"
JSON_OPENERS = ("{", "[")
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
    shaped: dict[str, Any] = {"when": when, "algorithm_id": str(details.get("algorithm_id") or "")}
    parameters = details.get("parameters")
    if isinstance(parameters, dict) and isinstance(parameters.get("inputs"), dict):
        parameters = parameters["inputs"]
    if isinstance(parameters, dict):
        kept = list(parameters.items())[:MAX_PARAMETERS]
        shaped["parameters"] = {str(key): _masked(key, value, 0) for key, value in kept}
        named = _named_layers(dict(kept), layers)
        if named:
            shaped["project_layers"] = named
    elif details.get("python_command"):
        shaped["python_command"] = shorten(str(details["python_command"]))
    results = details.get("results")
    shaped["finished"] = isinstance(results, dict)
    if isinstance(results, dict):
        kept_results = {str(key): value for key, value in results.items() if key not in MODEL_RESULT_KEYS}
        shaped["results"] = {key: _masked(key, value, 0) for key, value in kept_results.items()}
        named = _named_layers(kept_results, layers)
        if named:
            shaped["result_layers"] = named
    return shaped


def shorten(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        structure = _json_structure(value)
        if structure is not None:
            return _clipped(json.dumps(shorten(structure, depth + 1), ensure_ascii=False))
        # A layer parameter is recorded as its whole source, keys and passwords included.
        return _clipped(sanitize_source(value))
    if isinstance(value, (list, tuple, dict)) and depth >= MAX_DEPTH:
        return ELIDED
    if isinstance(value, (list, tuple)):
        items = [shorten(item, depth + 1) for item in value[:MAX_LIST_ITEMS]]
        return items + [ELIDED] if len(value) > MAX_LIST_ITEMS else items
    if isinstance(value, dict):
        return {str(key): _masked(key, item, depth + 1) for key, item in list(value.items())[:MAX_LIST_ITEMS]}
    return shorten(str(value), depth)


def _masked(key: Any, value: Any, depth: int) -> Any:
    return MASKED_VALUE if is_secret_name(str(key)) else shorten(value, depth)


def _json_structure(text: str) -> Any:
    stripped = text.strip()
    if not stripped.startswith(JSON_OPENERS):
        return None
    try:
        parsed = json.loads(stripped)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _clipped(text: str) -> str:
    return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - 1] + ELIDED


def project_layer_names() -> dict[str, str]:
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
