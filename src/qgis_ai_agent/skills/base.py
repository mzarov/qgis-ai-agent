from dataclasses import dataclass, field

FRONTMATTER_DELIMITER = "---"


@dataclass
class Skill:
    """Пакет знаний домена: описание для выбора и тело, грузящееся по требованию."""
    name: str
    description: str
    body: str = ""
    tool_names: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        """Однострочник для постоянной части системного промпта."""
        return f"- {self.name}: {self.description}"


def parse_skill_markdown(text: str, fallback_name: str = "") -> Skill:
    """
    Разбирает SKILL.md: фронтматтер между `---` плюс тело.
    Парсер на stdlib — PyYAML нет среди зависимостей плагина.
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    meta: dict[str, object] = {}
    body = raw

    lines = raw.split("\n")
    if lines and lines[0].strip() == FRONTMATTER_DELIMITER:
        for index in range(1, len(lines)):
            if lines[index].strip() == FRONTMATTER_DELIMITER:
                meta = _parse_frontmatter(lines[1:index])
                body = "\n".join(lines[index + 1 :]).strip("\n")
                break

    name = str(meta.get("name") or fallback_name).strip()
    tools = meta.get("tools")
    return Skill(
        name=name,
        description=str(meta.get("description") or "").strip(),
        body=body.strip(),
        tool_names=list(tools) if isinstance(tools, list) else [],
    )


def _parse_frontmatter(lines: list[str]) -> dict[str, object]:
    """Читает пары `ключ: значение`, поддерживая инлайновые списки `[a, b]`."""
    meta: dict[str, object] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
            meta[key] = [item for item in items if item]
        else:
            meta[key] = value.strip("'\"")
    return meta
