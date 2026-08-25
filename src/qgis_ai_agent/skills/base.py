from dataclasses import dataclass, field

FRONTMATTER_DELIMITER = "---"


@dataclass
class Skill:
    name: str
    description: str
    body: str = ""
    tool_names: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return f"- {self.name}: {self.description}"


def parse_skill_markdown(text: str, fallback_name: str = "") -> Skill:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    meta, body = _split_frontmatter(raw)
    tools = meta.get("tools")
    return Skill(
        name=str(meta.get("name") or fallback_name).strip(),
        description=str(meta.get("description") or "").strip(),
        body=body.strip(),
        tool_names=list(tools) if isinstance(tools, list) else [],
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    lines = raw.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, raw
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return _parse_frontmatter(lines[1:index]), "\n".join(lines[index + 1 :])
    return {}, raw


def _parse_frontmatter(lines: list[str]) -> dict[str, object]:
    meta: dict[str, object] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key:
            meta[key] = _parse_value(value.strip())
    return meta


def _parse_value(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
        return [item for item in items if item]
    return value.strip("'\"")
