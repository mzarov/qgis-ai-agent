from typing import Any

from qgis_ai_agent.qgis_tools.base import BaseTool
from qgis_ai_agent.qgis_tools.layout import LAYOUT_TOOLS

ALL_TOOLS: list[BaseTool] = [
    *LAYOUT_TOOLS,
]


def get_tool_by_name(name: str) -> BaseTool | None:
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None


def build_tools_prompt_section() -> str:
    """Формирует блок системного промпта с описанием всех инструментов."""
    lines = ["Доступные инструменты (порядок важен):"]
    for i, tool in enumerate(ALL_TOOLS, 1):
        lines.append(f"{i}) {tool.get_schema_for_prompt()}")
    return "\n".join(lines)


def execute_step(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Выполняет один шаг плана. Возвращает результат тула (например layout_name)."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        raise ValueError(f"Неизвестный инструмент: {tool_name}")
    return tool.execute(params)


def export_tool_manifest() -> list[dict[str, Any]]:
    """Экспортирует декларативный манифест всех тулов."""
    return [tool.get_manifest() for tool in ALL_TOOLS]


def build_tool_manifest_for_prompt() -> str:
    """Формирует компактный блок с capability-контекстом тулов для prompt."""
    lines = ["Доступные capability тулов:"]
    for tool in ALL_TOOLS:
        manifest = tool.get_manifest()
        caps = ", ".join(manifest["capabilities"]) if manifest["capabilities"] else "general"
        lines.append(f"- {manifest['name']}: {manifest['description']} | capabilities: {caps}")
        if manifest["constraints"]:
            lines.append(f"  constraints: {', '.join(manifest['constraints'])}")
    return "\n".join(lines)


def validate_plan_steps(steps: list[dict[str, Any]]) -> list[str]:
    """Проверяет план шагов относительно реестра тулов и обязательных параметров."""
    errors: list[str] = []
    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool")
        tool = get_tool_by_name(tool_name or "")
        if not tool:
            errors.append(f"Шаг {i}: неизвестный tool '{tool_name}'.")
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            errors.append(f"Шаг {i}: params должен быть объектом.")
            continue
        required_fields = [p["name"] for p in tool.params_schema if p.get("required", True)]
        for field in required_fields:
            if field not in params:
                errors.append(f"Шаг {i}: не хватает обязательного параметра '{field}' для '{tool_name}'.")
    return errors


def format_steps_for_display(steps: list[dict[str, Any]]) -> list[str]:
    """Превращает список шагов в человекочитаемые строки для чата."""
    result = []
    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool", "?")
        params = step.get("params") or {}
        tool = get_tool_by_name(tool_name)
        if tool_name == "create_layout":
            name = params.get("layout_name", "Макет")
            size = params.get("page_size", "A4")
            orient = params.get("orientation", "portrait")
            orient_ru = "альбомная" if orient == "landscape" else "книжная"
            result.append(f"{i}. Создать макет «{name}», {size} {orient_ru}.")
        elif tool_name == "add_map":
            x, y = params.get("x", 20), params.get("y", 40)
            w, h = params.get("width", 170), params.get("height", 120)
            result.append(f"{i}. Добавить карту: позиция ({x}, {y}) мм, размер {w}×{h} мм.")
        elif tool_name == "add_legend":
            x, y = params.get("x", 20), params.get("y", 165)
            title = params.get("title", "")
            t = f", заголовок «{title}»" if title else ""
            result.append(f"{i}. Добавить легенду: ({x}, {y}) мм{t}.")
        elif tool_name == "add_scale_bar":
            x, y = params.get("x", 20), params.get("y", 290)
            style = params.get("style", "Single Box")
            result.append(f"{i}. Добавить масштабную линейку: ({x}, {y}) мм, стиль «{style}».")
        elif tool_name == "add_label":
            text = params.get("text", "")
            alignment = params.get("alignment", "left")
            result.append(f"{i}. Добавить надпись «{text[:30]}{'…' if len(text) > 30 else ''}» (выравнивание: {alignment}).")
        else:
            tool = get_tool_by_name(tool_name)
            desc = tool.description if tool else tool_name
            result.append(f"{i}. {desc}: {params}")
    return result
