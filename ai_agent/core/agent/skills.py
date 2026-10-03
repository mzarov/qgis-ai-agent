from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.base import BaseTool
from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import LOCAL, SKILL_REGISTRY


def requested_skills(arguments: dict) -> list[str]:
    """Skill names from a load_skill call: `names` (a list) or the older single `name`."""
    raw = arguments.get("names")
    if raw is None:
        raw = [arguments.get("name")]
    if isinstance(raw, str):
        raw = [raw]
    names: list[str] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


MAX_SKILLS_PER_LOAD = 4
TOO_MANY_SKILLS = (
    "That asks for {count} skills at once. Load only the skills this task needs, at most {limit} per call; "
    "every loaded skill adds its rules and tools to every following request."
)


def load_skill(call: ToolCall, loaded_skills: list[str], images: bool = True) -> tuple[ToolResult, list[str]]:
    requested = [name for name in requested_skills(call.arguments) if name not in loaded_skills] or requested_skills(
        call.arguments
    )
    if len(requested) > MAX_SKILLS_PER_LOAD:
        message = TOO_MANY_SKILLS.format(count=len(requested), limit=MAX_SKILLS_PER_LOAD)
        return ToolResult(call=call, ok=False, payload={"error": message}), []
    known = [name for name in requested if SKILL_REGISTRY.get(name)]
    unknown = [name for name in requested if name not in known]
    if not known:
        missing = ", ".join(unknown) or "(none given)"
        return (
            ToolResult(
                call=call,
                ok=False,
                payload={"error": f"Skill not found: {missing}.", "available": SKILL_REGISTRY.names()},
            ),
            [],
        )
    newly_loaded = []
    for name in known:
        if name not in loaded_skills:
            extend_loaded(loaded_skills, name)
            newly_loaded.append(name)
    payload: dict = {"loaded": known, "tools": [tool.name for tool in tools_for_skills(known, images)]}
    if unknown:
        payload.update({"not_found": unknown, "available": SKILL_REGISTRY.names()})
    return ToolResult(call=call, ok=True, payload=payload), newly_loaded


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


def tools_for_skills(loaded_skills, images: bool = True) -> list[BaseTool]:
    """The tools the loaded skills offer; without images, the ones that only return a picture drop out."""
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
    return [
        tool
        for tool in ALL_TOOLS
        if (tool.skill in domains or tool.name in named) and (images or not tool.returns_image)
    ]


def _named_tools(names) -> list[BaseTool]:
    wanted = set(names)
    return [tool for tool in ALL_TOOLS if tool.name in wanted]
