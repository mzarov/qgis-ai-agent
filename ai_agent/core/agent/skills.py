from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.base import BaseTool
from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import LOCAL, SKILL_REGISTRY


def load_skill(call: ToolCall, loaded_skills: list[str]) -> tuple[ToolResult, str]:
    name = str(call.arguments.get("name") or "").strip()
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return (
            ToolResult(
                call=call,
                ok=False,
                payload={"error": f"Skill not found: {name}.", "available": SKILL_REGISTRY.names()},
            ),
            "",
        )
    newly_loaded = ""
    if name not in loaded_skills:
        extend_loaded(loaded_skills, name)
        newly_loaded = name
    tools = [tool.name for tool in tools_for_skills([name])]
    result = ToolResult(call=call, ok=True, payload={"loaded": name, "tools": tools})
    return result, newly_loaded


def extend_loaded(loaded_skills: list[str], name: str) -> None:
    for entry in skills_to_load(name):
        if entry not in loaded_skills:
            loaded_skills.append(entry)


def skills_to_load(name: str) -> list[str]:
    skill = SKILL_REGISTRY.get(name)
    if skill is None:
        return []
    names = [skill.name]
    if skill.origin == LOCAL:
        for tool in _named_tools(skill.tool_names):
            if tool.skill and tool.skill not in names and SKILL_REGISTRY.get(tool.skill) is not None:
                names.append(tool.skill)
    return names


def tools_for_skills(loaded_skills) -> list[BaseTool]:
    domains: set[str] = set()
    named: set[str] = set()
    for name in loaded_skills:
        skill = SKILL_REGISTRY.get(name)
        if skill is None:
            continue
        if skill.origin == LOCAL:
            named.update(skill.tool_names)
        else:
            domains.add(skill.name)
    return [tool for tool in ALL_TOOLS if tool.skill in domains or tool.name in named]


def _named_tools(names) -> list[BaseTool]:
    wanted = set(names)
    return [tool for tool in ALL_TOOLS if tool.name in wanted]
