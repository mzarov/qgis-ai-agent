import os
import re

from ai_agent.skills.base import Skill, parse_skill_markdown

SKILL_FILENAME = "SKILL.md"
SUMMARIES_HEADER = "Available skills (load one before acting in its domain):"
BUILTIN = "builtin"
LOCAL = "local"
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PROBLEM_NO_NAME = "{entry}: SKILL.md has no name"
PROBLEM_BAD_NAME = "{entry}: name '{name}' must be lowercase letters, digits, - or _"
PROBLEM_NO_DESCRIPTION = "{entry}: SKILL.md has no description"
PROBLEM_COLLISION = "{entry}: name '{name}' is taken by a built-in skill"
PROBLEM_DUPLICATE = "{entry}: name '{name}' is already used by another local skill"


class SkillRegistry:
    def __init__(self, root: str | None = None):
        self._root = root or os.path.dirname(os.path.abspath(__file__))
        self._skills: dict[str, Skill] | None = None
        self._local_root: str | None = None
        self._local: dict[str, Skill] = {}
        self._local_problems: list[str] = []

    def all_skills(self) -> list[Skill]:
        merged = {**self._local, **self._load()}
        return [merged[name] for name in sorted(merged)]

    def get(self, name: str) -> Skill | None:
        key = (name or "").strip()
        return self._load().get(key) or self._local.get(key)

    def names(self) -> list[str]:
        return sorted({*self._load(), *self._local})

    def local_names(self) -> list[str]:
        return sorted(self._local)

    def local_root(self) -> str | None:
        return self._local_root

    def local_problems(self) -> list[str]:
        return list(self._local_problems)

    def set_local_root(self, path: str | None) -> list[str]:
        self._local_root = path or None
        return self.refresh_local()

    def refresh_local(self) -> list[str]:
        self._local = {}
        self._local_problems = []
        if self._local_root:
            self._discover_local()
        return self.local_problems()

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
        for entry in self._entries(self._root):
            skill = self._read(self._root, entry, fallback_name=entry)
            if skill and skill.name:
                skills[skill.name] = skill
        return skills

    def _discover_local(self) -> None:
        builtin = self._load()
        for entry in self._entries(self._local_root or ""):
            skill = self._read(self._local_root or "", entry)
            if skill is None:
                continue
            problem = self._local_problem(entry, skill, builtin)
            if problem:
                self._local_problems.append(problem)
                continue
            skill.origin = LOCAL
            self._local[skill.name] = skill

    def _local_problem(self, entry: str, skill: Skill, builtin: dict[str, Skill]) -> str:
        if not skill.name:
            return PROBLEM_NO_NAME.format(entry=entry)
        if not SKILL_NAME_PATTERN.match(skill.name):
            return PROBLEM_BAD_NAME.format(entry=entry, name=skill.name)
        if not skill.description:
            return PROBLEM_NO_DESCRIPTION.format(entry=entry)
        if skill.name in builtin:
            return PROBLEM_COLLISION.format(entry=entry, name=skill.name)
        if skill.name in self._local:
            return PROBLEM_DUPLICATE.format(entry=entry, name=skill.name)
        return ""

    @staticmethod
    def _entries(root: str) -> list[str]:
        try:
            return sorted(os.listdir(root))
        except OSError:
            return []

    @staticmethod
    def _read(root: str, entry: str, fallback_name: str = "") -> Skill | None:
        path = os.path.join(root, entry, SKILL_FILENAME)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                return parse_skill_markdown(handle.read(), fallback_name=fallback_name)
        except (OSError, UnicodeDecodeError):
            return None


SKILL_REGISTRY = SkillRegistry()
