import json
import uuid
from collections.abc import Callable
from typing import Any, Final

from ai_agent.core.settings import get_history_days
from ai_agent.core.state.session import MODEL_ROLES, Session, StoredMessage
from ai_agent.core.state.store import SessionStore, current_project_key
from ai_agent.core.state.trace import PENDING, PLAN_ROLE, TRACE_ROLE, TraceLog

SUMMARY_INTRO = "Summary of our conversation so far, written when it was compacted to save space:\n"
# Chat templates reject two user turns in a row: the summary gets an assistant reply.
SUMMARY_ACK = "Understood. I will continue from this summary."
KEEP_AFTER_COMPACTION = 2
VISUAL_ROLE = "visual"
FAILURE_ROLE = "failure"
DISPLAY_ROLES = frozenset({VISUAL_ROLE, TRACE_ROLE, PLAN_ROLE, FAILURE_ROLE})
CHOSEN: Final = "chosen"
PLACE = "place"


class ConversationState:
    def __init__(self, store: SessionStore | None = None):
        self._store = store or SessionStore()
        self._session = Session.create(current_project_key())
        self.trace = TraceLog()

    def watch_saving(self, failed: Callable[[str], None]) -> None:
        self._store.on_failure = failed

    @property
    def messages(self) -> list[StoredMessage]:
        return self._session.messages

    @property
    def session_identifier(self) -> str:
        return self._session.identifier

    @property
    def project_key(self) -> str:
        return self._session.project

    @property
    def context_tokens(self) -> int:
        return self._session.context_tokens

    @property
    def spent_tokens(self) -> int:
        return self._session.spent_tokens

    @property
    def requests(self) -> int:
        return self._session.requests

    def window(self) -> list[dict[str, str]]:
        session = self._session
        head: list[dict[str, str]] = []
        if session.summary:
            head = [
                {"role": "user", "content": SUMMARY_INTRO + session.summary},
                {"role": "assistant", "content": SUMMARY_ACK},
            ]
        recent = session.messages[session.summary_index :]
        return head + [
            {"role": message["role"], "content": message["content"]}
            for message in recent
            if message.get("role") in MODEL_ROLES
        ]

    def add_visual(self, spec: dict[str, Any]) -> None:
        self.add(VISUAL_ROLE, json.dumps(spec, ensure_ascii=False))

    def add_failure(self, record: dict[str, Any]) -> None:
        self.add(FAILURE_ROLE, json.dumps(record, ensure_ascii=False))

    def drop_failures(self) -> None:
        messages = self._session.messages
        index = len(messages) - 1
        dropped = False
        while index >= 0 and messages[index].get("role") != "user":
            if messages[index].get("role") == FAILURE_ROLE:
                del messages[index]
                dropped = True
            index -= 1
        if dropped:
            self._store.save(self._session)

    def replayable(self) -> list[dict[str, Any]]:
        shown: list[dict[str, Any]] = []
        for index, message in enumerate(self._session.messages):
            role = message.get("role")
            if role == "user":
                shown.append({**message, PLACE: self._session.trimmed + index})
                continue
            if role not in DISPLAY_ROLES:
                shown.append(dict(message))
                continue
            data = _decoded(message)
            if data is not None:
                shown.append({"role": role, role: data})
        return shown

    def add(self, role: str, text: str, chosen: bool = False) -> None:
        self.keep_trace()
        self._session.add(role, text)
        if chosen and self._session.messages and self._session.messages[-1].get("role") == role:
            self._session.messages[-1][CHOSEN] = True
        self._store.save(self._session)

    def keep_trace(self) -> None:
        record = self.trace.take()
        if record is not None:
            self._session.add(TRACE_ROLE, json.dumps(record, ensure_ascii=False))
            self._store.save(self._session)

    def add_plan(self, lines: list[str], layer: str = "") -> str:
        key = uuid.uuid4().hex[:12]
        record = {"key": key, "lines": list(lines), "layer": layer, "state": PENDING, "marks": [], "at": ""}
        self.add(PLAN_ROLE, json.dumps(record, ensure_ascii=False))
        return key

    def update_plan(self, key: str, **changes: Any) -> None:
        for message in reversed(self._session.messages):
            record = _decoded(message) if message.get("role") == PLAN_ROLE else None
            if record is not None and record.get("key") == key:
                record.update(changes)
                message["content"] = json.dumps(record, ensure_ascii=False)
                self._store.save(self._session)
                return

    def count_turn(self, prompt_tokens: int, completion_tokens: int, measure: bool = True) -> None:
        if measure and prompt_tokens > 0:
            self._session.context_tokens = prompt_tokens
        self._session.spent_tokens += max(0, prompt_tokens) + max(0, completion_tokens)
        self._session.requests += 1
        self._store.save(self._session)

    @property
    def next_place(self) -> int:
        return self._session.end

    def message_at(self, place: int) -> StoredMessage | None:
        return self._session.at(place)

    def last_place(self, role: str) -> int | None:
        messages = self._session.messages
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == role:
                return self._session.trimmed + index
        return None

    def compact(self, summary: str, upto: int | None = None) -> None:
        self._session.compact(summary, KEEP_AFTER_COMPACTION, upto)
        self._store.save(self._session)

    def truncate(self, place: int) -> None:
        self._session.truncate(place)
        self._store.save(self._session)

    def set_context(self, tokens: int) -> None:
        self._session.context_tokens = max(0, tokens)
        self._store.save(self._session)

    def add_scoped(self, scope: tuple[str, str], role: str, text: str) -> bool:
        project, identifier = scope
        if (self.project_key, self.session_identifier) == scope:
            self.add(role, text)
            return True
        session = self._store.load(identifier)
        if session is None or session.project != project:
            return False
        session.add(role, text)
        self._store.save(session)
        return True

    @property
    def named(self) -> bool:
        return self._session.named

    @property
    def title(self) -> str:
        return self._session.display_title() if self._session.messages else ""

    def rename(self, identifier: str, title: str) -> bool:
        session = self._own(identifier)
        if session is None or not session.rename(title):
            return False
        self._store.save(session)
        return True

    def _own(self, identifier: str) -> Session | None:
        if identifier == self.session_identifier:
            return self._session
        session = self._store.load(identifier)
        return session if session is not None and session.project == self.project_key else None

    def delete(self, identifier: str) -> bool:
        if identifier == self.session_identifier:
            self._store.delete(identifier)
            self.trace.drop()
            self._adopt(Session.create(self.project_key))
            return True
        session = self._store.load(identifier)
        if session is not None and session.project == self.project_key:
            self._store.delete(identifier)
        return False

    def save(self) -> None:
        self._store.save(self._session)

    def prune_history(self) -> None:
        self._store.prune(get_history_days(), keep=self.session_identifier)

    def recent(self) -> list[tuple[str, str, float, bool]]:
        return [
            (
                session.identifier,
                session.display_title(),
                session.updated,
                session.identifier == self.session_identifier,
            )
            for session in self._store.recent(self.project_key)
        ]

    def start_new(self) -> None:
        self.keep_trace()
        self.save()
        self._adopt(Session.create(self.project_key))

    def sync_project(self, force_new: bool = False) -> bool:
        key = current_project_key()
        if not force_new and key == self.project_key:
            return False
        self.keep_trace()
        self.save()
        self._adopt(Session.create(key))
        return True

    def restore(self, identifier: str) -> bool:
        session = self._store.load(identifier)
        if session is None or session.project != self.project_key:
            return False
        self.keep_trace()
        self.save()
        self._adopt(session)
        return True

    def _adopt(self, session: Session) -> None:
        self._session = session


def _decoded(message: StoredMessage) -> dict[str, Any] | None:
    try:
        data = json.loads(message.get("content") or "")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
