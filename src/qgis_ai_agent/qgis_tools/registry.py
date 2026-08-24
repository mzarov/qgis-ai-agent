from typing import Any, Iterable

from qgis_ai_agent.qgis_tools.base import BaseTool
from qgis_ai_agent.qgis_tools.inspect import INSPECT_TOOLS
from qgis_ai_agent.qgis_tools.layout import LAYOUT_TOOLS
from qgis_ai_agent.qgis_tools.processing import PROCESSING_TOOLS

ALL_TOOLS: list[BaseTool] = [
    *INSPECT_TOOLS,
    *LAYOUT_TOOLS,
    *PROCESSING_TOOLS,
]


def get_tool_by_name(name: str) -> BaseTool | None:
    """Находит тул по имени или возвращает None."""
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None


def get_tools_for_skills(skill_names: Iterable[str]) -> list[BaseTool]:
    """Возвращает тулы, принадлежащие указанным скиллам, в порядке реестра."""
    wanted = {name for name in skill_names if name}
    return [tool for tool in ALL_TOOLS if tool.skill in wanted]


def build_tool_schemas(tools: Iterable[BaseTool]) -> list[dict[str, Any]]:
    """Собирает схемы тулов в формате OpenAI function calling."""
    return [tool.get_openai_schema() for tool in tools]


def execute_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Выполняет один вызов тула. Возвращает результат для агентного цикла."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        raise ValueError(f"Неизвестный инструмент: {tool_name}")
    return tool.execute(params)


def summarize_tool_call(tool_name: str, params: dict[str, Any]) -> str:
    """Человекочитаемое описание вызова тула для чата."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        return f"{tool_name}: {params}"
    return tool.summarize_call(params)


def export_tool_manifest() -> list[dict[str, Any]]:
    """Экспортирует декларативный манифест всех тулов."""
    return [tool.get_manifest() for tool in ALL_TOOLS]
