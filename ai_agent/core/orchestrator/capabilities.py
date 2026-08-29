from typing import Any

from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import SKILL_REGISTRY


def describe_capabilities() -> list[dict[str, Any]]:
    by_skill: dict[str, list[Any]] = {}
    for tool in ALL_TOOLS:
        by_skill.setdefault(tool.skill, []).append(tool)
    described = []
    for skill in SKILL_REGISTRY.all_skills():
        tools = by_skill.get(skill.name, [])
        described.append(
            {
                "name": skill.name,
                "description": skill.description,
                "tools": [
                    {
                        "name": tool.name,
                        "safety": tool.safety,
                        "network_access": bool(getattr(tool, "network_access", False)),
                        "description": tool.description,
                    }
                    for tool in sorted(tools, key=lambda item: item.name)
                ],
            }
        )
    return described
