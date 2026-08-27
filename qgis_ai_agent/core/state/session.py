import time
import uuid
from dataclasses import dataclass, field
from typing import Any

MAX_MESSAGES = 200
TITLE_LIMIT = 48
UNTITLED = "Без названия"
NO_PROJECT = "без проекта"


@dataclass
class Session:
    identifier: str
    project: str
    title: str = ""
    created: float = 0.0
    updated: float = 0.0
    messages: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def create(cls, project: str) -> "Session":
        now = time.time()
        return cls(
            identifier=uuid.uuid4().hex[:12],
            project=project or NO_PROJECT,
            created=now,
            updated=now,
        )

    @property
    def is_empty(self) -> bool:
        return not self.messages

    def add(self, role: str, text: str) -> None:
        content = (text or "").strip()
        if not content:
            return
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]
        self.updated = time.time()
        if not self.title and role == "user":
            self.title = shorten(content)

    def display_title(self) -> str:
        return self.title or UNTITLED

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "project": self.project,
            "title": self.title,
            "created": self.created,
            "updated": self.updated,
            "messages": self.messages,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Session | None":
        identifier = str(raw.get("identifier") or "").strip()
        if not identifier:
            return None
        messages = [
            {"role": str(item.get("role", "")), "content": str(item.get("content", ""))}
            for item in raw.get("messages") or []
            if isinstance(item, dict) and item.get("content")
        ]
        return cls(
            identifier=identifier,
            project=str(raw.get("project") or NO_PROJECT),
            title=str(raw.get("title") or ""),
            created=_as_float(raw.get("created")),
            updated=_as_float(raw.get("updated")),
            messages=messages[-MAX_MESSAGES:],
        )


def shorten(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= TITLE_LIMIT:
        return flat
    return flat[:TITLE_LIMIT].rstrip() + "…"


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
