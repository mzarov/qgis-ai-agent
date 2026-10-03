import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ai_agent.i18n import tr

MAX_MESSAGES = 200
TITLE_LIMIT = 48
UNTITLED = tr("Untitled")
NO_PROJECT = "no project"


@dataclass
class Session:
    identifier: str
    project: str
    title: str = ""
    created: float = 0.0
    updated: float = 0.0
    messages: list[dict[str, str]] = field(default_factory=list)
    # Messages before `summary_index` reach the model only through `summary` (see compact()).
    summary: str = ""
    summary_index: int = 0
    # The prompt size of the latest model request and the tokens this conversation spent.
    context_tokens: int = 0
    spent_tokens: int = 0
    requests: int = 0

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
            self.summary_index = max(0, self.summary_index - dropped)
        self.updated = time.time()
        if not self.title and role == "user":
            self.title = shorten(content)

    def compact(self, summary: str, keep: int, upto: int | None = None) -> None:
        """Let `summary` stand for the first `upto` messages but their last `keep`, starting at a user message.

        `upto` is the length the summarised history had: messages added while the
        summary was being written stay in the window.
        """
        covered = len(self.messages) if upto is None else min(max(0, upto), len(self.messages))
        start = max(0, covered - max(0, keep))
        while start < len(self.messages) and self.messages[start]["role"] != "user":
            start += 1
        self.summary = summary.strip()
        self.summary_index = start
        self.updated = time.time()

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
            "summary": self.summary,
            "summary_index": self.summary_index,
            "context_tokens": self.context_tokens,
            "spent_tokens": self.spent_tokens,
            "requests": self.requests,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Session | None":
        identifier = str(raw.get("identifier") or "").strip()
        if not identifier:
            return None
        raw_messages = raw.get("messages")
        if not isinstance(raw_messages, list):
            raw_messages = []
        messages = [
            {"role": str(item.get("role", "")), "content": str(item.get("content", ""))}
            for item in raw_messages
            if isinstance(item, dict) and item.get("content")
        ]
        return cls(
            identifier=identifier,
            project=str(raw.get("project") or NO_PROJECT),
            title=str(raw.get("title") or ""),
            created=_as_float(raw.get("created")),
            updated=_as_float(raw.get("updated")),
            messages=messages[-MAX_MESSAGES:],
            summary=str(raw.get("summary") or ""),
            summary_index=min(_as_int(raw.get("summary_index")), len(messages[-MAX_MESSAGES:])),
            context_tokens=_as_int(raw.get("context_tokens")),
            spent_tokens=_as_int(raw.get("spent_tokens")),
            requests=_as_int(raw.get("requests")),
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


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
