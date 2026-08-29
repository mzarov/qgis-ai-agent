from collections.abc import Iterable
from typing import Any

from qgis_ai_agent.qgis_tools.base import BaseTool
from qgis_ai_agent.qgis_tools.edit import EDIT_TOOLS
from qgis_ai_agent.qgis_tools.fields import FIELDS_TOOLS
from qgis_ai_agent.qgis_tools.inspect import INSPECT_TOOLS
from qgis_ai_agent.qgis_tools.layout import LAYOUT_TOOLS
from qgis_ai_agent.qgis_tools.osm import OSM_TOOLS
from qgis_ai_agent.qgis_tools.processing import PROCESSING_TOOLS
from qgis_ai_agent.qgis_tools.project import PROJECT_TOOLS
from qgis_ai_agent.qgis_tools.python import PYTHON_TOOLS
from qgis_ai_agent.qgis_tools.style import STYLE_TOOLS
from qgis_ai_agent.qgis_tools.web import WEB_TOOLS

ALL_TOOLS: list[BaseTool] = [
    *INSPECT_TOOLS,
    *PROJECT_TOOLS,
    *OSM_TOOLS,
    *WEB_TOOLS,
    *STYLE_TOOLS,
    *PROCESSING_TOOLS,
    *EDIT_TOOLS,
    *LAYOUT_TOOLS,
    *PYTHON_TOOLS,
    *FIELDS_TOOLS,
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
    return tool.execute(params)


def prepare_tool_call(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    return _require_tool(tool_name).prepare(params)


def summarize_tool_call(tool_name: str, params: dict[str, Any]) -> str:
    tool = get_tool_by_name(tool_name)
    if not tool:
        return f"{tool_name}: {params}"
    return tool.summarize_call(params)


def _require_tool(tool_name: str) -> BaseTool:
    tool = get_tool_by_name(tool_name)
    if not tool:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tool
