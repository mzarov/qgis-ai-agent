from ai_agent.core.local_skills import register_local_skills, skill_choices
from ai_agent.skills.registry import SKILL_REGISTRY

SLASH = "/"
DEFAULT_SKILL_PROMPT = "Apply the '{name}' skill to the current project."


def parse_slash(text: str) -> tuple[str, str]:
    stripped = (text or "").lstrip()
    if not stripped.startswith(SLASH):
        return "", text
    parts = stripped[len(SLASH) :].split(None, 1)
    name = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    return name, rest


def is_known_skill(name: str) -> bool:
    register_local_skills()
    return SKILL_REGISTRY.get(name) is not None


def prompt_for(name: str, rest: str) -> str:
    return rest or DEFAULT_SKILL_PROMPT.format(name=name)


def available_names() -> str:
    return ", ".join(SLASH + name for name in SKILL_REGISTRY.names())


def choices() -> list[tuple[str, str, str]]:
    return skill_choices()
