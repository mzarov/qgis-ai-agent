import time
import uuid
from dataclasses import dataclass, field
from typing import Any, NotRequired, TypedDict

from ai_agent.i18n import tr

MAX_MESSAGES = 400
TITLE_LIMIT = 48
UNTITLED = tr("Untitled")
NO_PROJECT = "no project"


class StoredMessage(TypedDict):
    role: str
    content: str
    chosen: NotRequired[bool]


@dataclass
class Session:
    identifier: str
    project: str
    title: str = ""
    created: float = 0.0
    updated: float = 0.0
    messages: list[StoredMessage] = field(default_factory=list)
    # A message's place (trimmed + index) never changes: rewind points and checkpoints hold places.
    trimmed: int = 0
    summary: str = ""
    summary_index: int = 0
    context_tokens: int = 0
    spent_tokens: int = 0
    requests: int = 0
    named: bool = False

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
            dropped = len(self.messages) - MAX_MESSAGES
            self.messages = self.messages[-MAX_MESSAGES:]
            self.trimmed += dropped
            self.summary_index = max(0, self.summary_index - dropped)
        self.updated = time.time()
        if not self.title and role == "user":
            self.title = shorten(content)

    @property
    def end(self) -> int:
        return self.trimmed + len(self.messages)

    def at(self, place: int) -> StoredMessage | None:
        index = place - self.trimmed
        return self.messages[index] if 0 <= index < len(self.messages) else None

    def compact(self, summary: str, keep: int, upto: int | None = None) -> None:
        covered = len(self.messages) if upto is None else min(max(0, upto - self.trimmed), len(self.messages))
        start = max(0, covered - max(0, keep))
        while start < len(self.messages) and self.messages[start]["role"] != "user":
            start += 1
        self.summary = summary.strip()
        self.summary_index = start
        self.updated = time.time()

    def truncate(self, place: int) -> None:
        self.messages = self.messages[: max(0, place - self.trimmed)]
        if self.summary_index > len(self.messages):
            self.summary = ""
            self.summary_index = 0
        self.context_tokens = 0
        self.updated = time.time()

    def rename(self, title: str) -> bool:
        cleaned = shorten(title)
        if not cleaned:
            return False
        self.title = cleaned
        self.named = True
        return True

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
            "trimmed": self.trimmed,
            "summary": self.summary,
            "summary_index": self.summary_index,
            "context_tokens": self.context_tokens,
            "spent_tokens": self.spent_tokens,
            "requests": self.requests,
            "named": self.named,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Session | None":
        identifier = str(raw.get("identifier") or "").strip()
        if not identifier:
            return None
        raw_messages = raw.get("messages")
        if not isinstance(raw_messages, list):
            raw_messages = []
        messages = [_stored(item) for item in raw_messages if isinstance(item, dict) and item.get("content")]
        return cls(
            identifier=identifier,
            project=str(raw.get("project") or NO_PROJECT),
            title=str(raw.get("title") or ""),
            created=_as_float(raw.get("created")),
            updated=_as_float(raw.get("updated")),
            messages=messages[-MAX_MESSAGES:],
            trimmed=_as_int(raw.get("trimmed")) + max(0, len(messages) - MAX_MESSAGES),
            summary=str(raw.get("summary") or ""),
            summary_index=min(_as_int(raw.get("summary_index")), len(messages[-MAX_MESSAGES:])),
            context_tokens=_as_int(raw.get("context_tokens")),
            spent_tokens=_as_int(raw.get("spent_tokens")),
            requests=_as_int(raw.get("requests")),
            named=bool(raw.get("named")),
        )


def _stored(item: dict[str, Any]) -> StoredMessage:
    message: StoredMessage = {"role": str(item.get("role", "")), "content": str(item.get("content", ""))}
    if item.get("chosen") is True:
        message["chosen"] = True
    return message


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


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
