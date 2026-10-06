from collections.abc import Iterable
from typing import Any

from ai_agent.qgis_tools.annotations import ANNOTATIONS_TOOLS
from ai_agent.qgis_tools.base import BaseTool
from ai_agent.qgis_tools.call_summary import CallSummary
from ai_agent.qgis_tools.charts import CHARTS_TOOLS
from ai_agent.qgis_tools.common.validation import validate_parameters
from ai_agent.qgis_tools.data import DATA_TOOLS
from ai_agent.qgis_tools.draw import DRAW_TOOLS
from ai_agent.qgis_tools.edit import EDIT_TOOLS
from ai_agent.qgis_tools.fields import FIELDS_TOOLS
from ai_agent.qgis_tools.inspect import INSPECT_TOOLS
from ai_agent.qgis_tools.layout import LAYOUT_TOOLS
from ai_agent.qgis_tools.osm import OSM_TOOLS
from ai_agent.qgis_tools.plugins import PLUGINS_TOOLS
from ai_agent.qgis_tools.processing import PROCESSING_TOOLS
from ai_agent.qgis_tools.project import PROJECT_TOOLS
from ai_agent.qgis_tools.python import PYTHON_TOOLS
from ai_agent.qgis_tools.style import STYLE_TOOLS
from ai_agent.qgis_tools.tables import TABLES_TOOLS
from ai_agent.qgis_tools.three_d import THREE_D_TOOLS
from ai_agent.qgis_tools.web import WEB_TOOLS

ALL_TOOLS: list[BaseTool] = [
    *INSPECT_TOOLS,
    *PROJECT_TOOLS,
    *OSM_TOOLS,
    *DATA_TOOLS,
    *WEB_TOOLS,
    *ANNOTATIONS_TOOLS,
    *THREE_D_TOOLS,
    *STYLE_TOOLS,
    *PROCESSING_TOOLS,
    *EDIT_TOOLS,
    *DRAW_TOOLS,
    *LAYOUT_TOOLS,
    *PYTHON_TOOLS,
    *FIELDS_TOOLS,
    *TABLES_TOOLS,
    *CHARTS_TOOLS,
    *PLUGINS_TOOLS,
]


def get_tool_by_name(name: str) -> BaseTool | None:
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None


def get_tools_for_skills(skill_names: Iterable[str]) -> list[BaseTool]:
    wanted = {name for name in skill_names if name}
    return [tool for tool in ALL_TOOLS if tool.skill in wanted]


def build_tool_schemas(tools: Iterable[BaseTool]) -> list[dict[str, Any]]:
    return [tool.get_openai_schema() for tool in tools]


def execute_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    tool = _require_tool(tool_name)
    validate_parameters(params, tool.params_schema)
    return tool.execute(params)


def prepare_tool_call(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    tool = _require_tool(tool_name)
    validate_parameters(params, tool.params_schema)
    return tool.prepare(params)


def validate_tool_arguments(tool_name: str, params: dict[str, Any]) -> None:
    tool = get_tool_by_name(tool_name)
    validate_parameters(params, tool.params_schema if tool is not None else ())


def summarize_tool_call(tool_name: str, params: dict[str, Any]) -> CallSummary:
    """The user-facing label of a call, with the spans that repeat its arguments marked."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        return CallSummary.marking(f"{tool_name}: {params}", {})
    try:
        summary = CallSummary.marking(tool.summarize_call(params), params if isinstance(params, dict) else {})
    except Exception:
        summary = CallSummary.marking(tool.name, {})
    summary.skill = tool.skill
    return summary


def summarize_tool_result(tool_name: str, params: dict[str, Any], payload: dict[str, Any]) -> str:
    """The user-facing line under a finished call, or "" when the tool has nothing short to say."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        return ""
    try:
        return str(tool.summarize_result(params, payload) or "")
    except Exception:
        return ""


def _require_tool(tool_name: str) -> BaseTool:
    tool = get_tool_by_name(tool_name)
    if not tool:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tool
