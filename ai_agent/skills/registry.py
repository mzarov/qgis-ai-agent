import os

from ai_agent.skills.base import Skill, parse_skill_markdown

SKILL_FILENAME = "SKILL.md"
SUMMARIES_HEADER = "Available skills (load one before acting in its domain):"


class SkillRegistry:
    def __init__(self, root: str | None = None):
        self._root = root or os.path.dirname(os.path.abspath(__file__))
        self._skills: dict[str, Skill] | None = None

    def all_skills(self) -> list[Skill]:
        skills = self._load()
        return [skills[name] for name in sorted(skills)]

    def get(self, name: str) -> Skill | None:
        return self._load().get((name or "").strip())

    def names(self) -> list[str]:
        return sorted(self._load())

    def summaries_block(self) -> str:
        skills = self.all_skills()
        if not skills:
            return ""
        return "\n".join([SUMMARIES_HEADER, *(skill.summary_line() for skill in skills)])

    def bodies_block(self, names) -> str:
        blocks = []
        for name in names:
            skill = self.get(name)
            if skill and skill.body:
                blocks.append(f"# Skill: {skill.name}\n{skill.body}")
        return "\n\n".join(blocks)

    def _load(self) -> dict[str, Skill]:
        if self._skills is None:
            self._skills = self._discover()
        return self._skills

    def _discover(self) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        for entry in self._entries():
            skill = self._read(entry)
            if skill and skill.name:
                skills[skill.name] = skill
        return skills

    def _entries(self) -> list[str]:
        try:
            return sorted(os.listdir(self._root))
        except OSError:
            return []

    def _read(self, entry: str) -> Skill | None:
        path = os.path.join(self._root, entry, SKILL_FILENAME)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                return parse_skill_markdown(handle.read(), fallback_name=entry)
        except OSError:
            return None


SKILL_REGISTRY = SkillRegistry()
