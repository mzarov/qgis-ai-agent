import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).with_name("fixture.json")
DESCRIBE_LAYER = "describe_layer"
FIELD_VALUES = "get_field_values"
DESCRIBE_ALGORITHM = "describe_processing"
DESCRIBE_STYLE = "describe_style"
LIST_PLUGINS = "list_plugins"
PROJECT_READS = ("list_layers", "get_project_info", "get_canvas_extent", "get_qgis_info")


def load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def answer(tool: str, arguments: dict[str, Any], data: dict[str, Any]) -> Any:
    if tool in (DESCRIBE_LAYER, DESCRIBE_STYLE):
        return _layer_entry(data[tool], arguments.get("layer_name"))
    if tool == FIELD_VALUES:
        fields = _layer_entry(data[FIELD_VALUES], arguments.get("layer_name")) or {}
        return fields.get(str(arguments.get("field_name") or "").strip())
    if tool == DESCRIBE_ALGORITHM:
        return data[DESCRIBE_ALGORITHM].get(str(arguments.get("algorithm_id") or "").strip())
    if tool in PROJECT_READS:
        return data[tool]
    if tool == LIST_PLUGINS:
        return _plugins(data[LIST_PLUGINS]["plugins"], arguments.get("query"))
    return None


def _layer_entry(table: dict[str, Any], name: Any) -> Any:
    wanted = str(name or "").strip()
    if wanted in table:
        return table[wanted]
    matches = [key for key in table if key.casefold() == wanted.casefold()]
    return table[matches[0]] if len(matches) == 1 else None


def _plugins(plugins: list[dict[str, Any]], query: Any) -> dict[str, Any]:
    words = str(query or "").lower().split()
    listed = [
        plugin
        for plugin in plugins
        if not words or any(word in " ".join(str(value) for value in plugin.values()).lower() for word in words)
    ]
    return {"plugins": listed, "count": len(listed)}
