import re

from ai_agent.core.local_skills import register_local_skills, skill_choices
from ai_agent.skills.registry import SKILL_REGISTRY

SLASH = "/"
COMMAND = re.compile(r"/([A-Za-z0-9_-]*)(?:\s+(.*))?\Z", re.DOTALL)
DEFAULT_SKILL_PROMPT = "Apply the '{name}' skill to the current project."


def parse_slash(text: str) -> tuple[str, str]:
    # A request may open with a path: only /name followed by a space or the end is a command.
    command = COMMAND.match((text or "").strip())
    if command is None:
        return "", text
    return command.group(1).lower(), (command.group(2) or "").strip()


def is_known_skill(name: str) -> bool:
    register_local_skills()
    return SKILL_REGISTRY.get(name) is not None


def prompt_for(name: str, rest: str) -> str:
    return rest or DEFAULT_SKILL_PROMPT.format(name=name)


def available_names() -> str:
    return ", ".join(SLASH + name for name in SKILL_REGISTRY.names())


def choices() -> list[tuple[str, str, str]]:
    return skill_choices()
