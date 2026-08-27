from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.skills.registry import SKILL_REGISTRY


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
        loaded_skills.append(name)
        newly_loaded = name
    result = ToolResult(call=call, ok=True, payload={"loaded": name, "tools": skill.tool_names})
    return result, newly_loaded
