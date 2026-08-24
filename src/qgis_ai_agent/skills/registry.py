import os

from qgis_ai_agent.skills.base import Skill, parse_skill_markdown

SKILL_FILENAME = "SKILL.md"


class SkillRegistry:
    """
    Реестр скиллов: находит пакеты `<skill>/SKILL.md` рядом с собой,
    отдаёт однострочники для промпта и тела скиллов по требованию.
    """

    def __init__(self, root: str | None = None):
        self._root = root or os.path.dirname(os.path.abspath(__file__))
        self._skills: dict[str, Skill] | None = None

    def _load(self) -> dict[str, Skill]:
        """Читает все SKILL.md один раз за сессию."""
        if self._skills is not None:
            return self._skills
        skills: dict[str, Skill] = {}
        try:
            entries = sorted(os.listdir(self._root))
        except OSError:
            entries = []
        for entry in entries:
            skill_path = os.path.join(self._root, entry, SKILL_FILENAME)
            if not os.path.isfile(skill_path):
                continue
            try:
                with open(skill_path, encoding="utf-8") as handle:
                    skill = parse_skill_markdown(handle.read(), fallback_name=entry)
            except OSError:
                continue
            if skill.name:
                skills[skill.name] = skill
        self._skills = skills
        return skills

    def all_skills(self) -> list[Skill]:
        """Все найденные скиллы в алфавитном порядке имён."""
        return [self._load()[name] for name in sorted(self._load())]

    def get(self, name: str) -> Skill | None:
        """Скилл по имени или None."""
        return self._load().get((name or "").strip())

    def names(self) -> list[str]:
        """Имена всех доступных скиллов."""
        return sorted(self._load())

    def summaries_block(self) -> str:
        """Постоянная часть промпта: по одной строке на скилл."""
        skills = self.all_skills()
        if not skills:
            return ""
        lines = ["Available skills (load one before acting in its domain):"]
        lines.extend(skill.summary_line() for skill in skills)
        return "\n".join(lines)

    def bodies_block(self, names) -> str:
        """Тела указанных скиллов — подмешиваются, когда скилл выбран."""
        blocks: list[str] = []
        for name in names:
            skill = self.get(name)
            if skill and skill.body:
                blocks.append(f"# Skill: {skill.name}\n{skill.body}")
        return "\n\n".join(blocks)


# Единственный реестр на процесс — файлы скиллов не меняются во время работы QGIS.
SKILL_REGISTRY = SkillRegistry()
