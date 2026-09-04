import os
from typing import Any

from qgis.core import QgsApplication

from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import SKILL_FILENAME, SKILL_REGISTRY

FOLDER_NAME = "ai_agent_skills"
EXAMPLE_FOLDER = "example-skill"
PROBLEM_UNKNOWN_TOOLS = "{name}: unknown tools ignored: {tools}"
EXAMPLE_SKILL = """---
name: example-skill
description: Rename me — one line saying when the agent should load this skill. The model picks skills by this sentence.
tools: [list_layers, describe_layer]
---

# Example skill

Write here the rules the agent must follow while this skill is loaded:
step order, units, pitfalls, house conventions. Plain Markdown, in English.

The tools list above is optional. Name existing tools to make them available
together with these rules; the domain rules of those tools load automatically.
Type /example-skill in the chat to invoke this skill explicitly.
"""


def local_skills_dir() -> str:
    base = QgsApplication.qgisSettingsDirPath()
    if not isinstance(base, str) or not base:
        return ""
    path = os.path.join(base, FOLDER_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return ""
    return path


def register_local_skills(path: str | None = None) -> list[str]:
    root = path if path is not None else local_skills_dir()
    problems = SKILL_REGISTRY.set_local_root(root or None)
    known = {tool.name for tool in ALL_TOOLS}
    for name in SKILL_REGISTRY.local_names():
        skill = SKILL_REGISTRY.get(name)
        if skill is None:
            continue
        unknown = [tool for tool in skill.tool_names if tool not in known]
        if unknown:
            skill.tool_names = [tool for tool in skill.tool_names if tool in known]
            problems.append(PROBLEM_UNKNOWN_TOOLS.format(name=name, tools=", ".join(unknown)))
    return problems


def describe_local_skills(path: str | None = None) -> dict[str, Any]:
    problems = register_local_skills(path)
    skills = []
    for name in SKILL_REGISTRY.local_names():
        skill = SKILL_REGISTRY.get(name)
        if skill is not None:
            skills.append({"name": skill.name, "description": skill.description, "tools": list(skill.tool_names)})
    return {"path": SKILL_REGISTRY.local_root() or "", "skills": skills, "problems": problems}


def write_example_skill(path: str | None = None) -> str:
    root = path if path is not None else local_skills_dir()
    if not root:
        return ""
    folder = os.path.join(root, EXAMPLE_FOLDER)
    target = os.path.join(folder, SKILL_FILENAME)
    if not os.path.exists(target):
        os.makedirs(folder, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(EXAMPLE_SKILL)
    return target


def skill_choices() -> list[tuple[str, str, str]]:
    register_local_skills()
    return [(skill.name, skill.description, skill.origin) for skill in SKILL_REGISTRY.all_skills()]
