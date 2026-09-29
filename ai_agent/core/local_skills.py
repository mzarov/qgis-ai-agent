import os
from typing import Any

from qgis.core import QgsApplication

from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import SKILL_FILENAME, SKILL_REGISTRY

FOLDER_NAME = "ai_agent_skills"
EXAMPLE_FOLDER = "house-style"
EXAMPLE_DESCRIPTION = (
    "EXAMPLE — replace this line with when to load the skill, e.g. when styling or exporting maps for our team."
)
PROBLEM_UNKNOWN_TOOLS = "{name}: unknown tools ignored: {tools}"
PROBLEM_EXAMPLE_INACTIVE = "{name}: still the example — edit its description to switch it on."
EXAMPLE_SKILL = f"""---
name: house-style
description: {EXAMPLE_DESCRIPTION}
tools: [set_symbol, set_labels, export_layout]
---

# House style (edit me)

- Roads: grey #6b6b6b, 0.4 mm; primary roads #d97b00, 0.8 mm.
- Labels: Arial, size 9, white buffer 1 mm.
- Print exports: PDF, A3 landscape, into the project folder.

How this file works. One folder per skill, and the file is always SKILL.md.
`name` is lowercase letters, digits, - or _ and becomes the /command. The
`description` is the one line the agent reads to decide when to load the
skill, so write it as "load when ...". `tools` is optional: it names existing
plugin tools to load together with these rules, with their own domain rules.
Write in English — the agent reads English best and still answers in your
language. This example stays switched off until you change its description.
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
        if skill.description.strip() == EXAMPLE_DESCRIPTION:
            SKILL_REGISTRY.drop_local(name)
            problems.append(PROBLEM_EXAMPLE_INACTIVE.format(name=name))
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
