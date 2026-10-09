import json
import uuid
from typing import Any

from ai_agent.core.state.session import Session
from ai_agent.core.state.store import SessionStore, current_project_key
from ai_agent.core.state.trace import PENDING, PLAN_ROLE, TRACE_ROLE, TraceLog

# Model-facing, so plain English: the summary opens the window as a user turn and an
# acknowledged one, because several chat templates reject two user turns in a row.
SUMMARY_INTRO = "Summary of our conversation so far, written when it was compacted to save space:\n"
SUMMARY_ACK = "Understood. I will continue from this summary."
KEEP_AFTER_COMPACTION = 2
# A chart or table the feed drew, kept so a reopened conversation shows it again; the model never gets it.
VISUAL_ROLE = "visual"
MODEL_ROLES = frozenset({"user", "assistant"})
# Display-only entries and the key each comes back under for the chat; the model's window skips them.
DISPLAY_KEYS = {VISUAL_ROLE: "visual", TRACE_ROLE: "trace", PLAN_ROLE: "plan"}
# A user message the user picked on a question card: the chat shows it as "You chose …" again.
CHOSEN = "chosen"


class ConversationState:
    """The conversation the chat shows and the window the model gets, through one entry point.

    The model gets the whole conversation for as long as it fits: no message count
    cap. When it stops fitting, compact() replaces older messages with a summary in
    the model's window; the saved conversation and the chat keep every message.
    """

    def __init__(self, store: SessionStore | None = None):
        self._store = store or SessionStore()
        self._session = Session.create(current_project_key())
        # The current turn's steps and reasoning, written before the next message (see state/trace.py).
        self.trace = TraceLog()

    @property
    def messages(self) -> list[dict[str, str]]:
        return self._session.messages

    @property
    def session_identifier(self) -> str:
        return self._session.identifier

    @property
    def project_key(self) -> str:
        return self._session.project

    @property
    def context_tokens(self) -> int:
        """What a request of this conversation costs before any tool runs: measured, or estimated."""
        return self._session.context_tokens

    @property
    def spent_tokens(self) -> int:
        return self._session.spent_tokens

    @property
    def requests(self) -> int:
        return self._session.requests

    def window(self) -> list[dict[str, str]]:
        session = self._session
        head = []
        if session.summary:
            head = [
                {"role": "user", "content": SUMMARY_INTRO + session.summary},
                {"role": "assistant", "content": SUMMARY_ACK},
            ]
        recent = session.messages[session.summary_index :]
        # Role and content only: a display flag on a message is not for any endpoint.
        return head + [
            {"role": message["role"], "content": message["content"]}
            for message in recent
            if message.get("role") in MODEL_ROLES
        ]

    def add_visual(self, spec: dict[str, Any]) -> None:
        self.add(VISUAL_ROLE, json.dumps(spec, ensure_ascii=False))

    def replayable(self) -> list[dict[str, Any]]:
        """The messages for the chat, each saved chart, table, turn trace or plan card decoded back."""
        shown: list[dict[str, Any]] = []
        for message in self._session.messages:
            role = message.get("role")
            if role not in DISPLAY_KEYS:
                shown.append(dict(message))
                continue
            try:
                data = json.loads(message.get("content") or "")
            except ValueError:
                continue
            if isinstance(data, dict):
                shown.append({"role": role, DISPLAY_KEYS[role]: data})
        return shown

    def add(self, role: str, text: str, chosen: bool = False) -> None:
        """Write a message; the turn's steps so far go first, so the chat replays them where they were."""
        self.keep_trace()
        self._session.add(role, text)
        if chosen and self._session.messages and self._session.messages[-1].get("role") == role:
            self._session.messages[-1][CHOSEN] = True
        self._store.save(self._session)

    def keep_trace(self) -> None:
        """Write the steps and reasoning recorded since the last message, if there were any."""
        record = self.trace.take()
        if record is not None:
            self._session.add(TRACE_ROLE, json.dumps(record, ensure_ascii=False))
            self._store.save(self._session)

    def add_plan(self, lines: list[str]) -> str:
        """Keep a plan card for the replay; the returned key settles it once it is applied or dropped."""
        key = uuid.uuid4().hex[:12]
        record = {"key": key, "lines": list(lines), "state": PENDING, "marks": [], "at": ""}
        self.add(PLAN_ROLE, json.dumps(record, ensure_ascii=False))
        return key

    def update_plan(self, key: str, **changes: Any) -> None:
        """Settle a kept plan card: its state, the time, every step's mark."""
        for message in reversed(self._session.messages):
            if message.get("role") != PLAN_ROLE:
                continue
            try:
                record = json.loads(message.get("content") or "")
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("key") == key:
                record.update(changes)
                message["content"] = json.dumps(record, ensure_ascii=False)
                self._store.save(self._session)
                return

    def count_turn(self, prompt_tokens: int, completion_tokens: int, measure: bool = True) -> None:
        """Record one model request; with `measure`, its prompt is the conversation's request size.

        Only a run's first request measures it: later ones carry that run's tool
        results, which the next run does not send again.
        """
        if measure and prompt_tokens > 0:
            self._session.context_tokens = prompt_tokens
        self._session.spent_tokens += max(0, prompt_tokens) + max(0, completion_tokens)
        self._session.requests += 1
        self._store.save(self._session)

    @property
    def message_count(self) -> int:
        return len(self._session.messages)

    def compact(self, summary: str, upto: int | None = None) -> None:
        """Let `summary` stand in for the first `upto` messages but the last exchange, in the model's window."""
        self._session.compact(summary, KEEP_AFTER_COMPACTION, upto)
        self._store.save(self._session)

    def truncate(self, index: int) -> None:
        """Forget the messages from `index` on, as if the conversation had stopped there."""
        self._session.truncate(index)
        self._store.save(self._session)

    def set_context(self, tokens: int) -> None:
        """An estimate of the context in use until the next request measures it."""
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
        """The open conversation's title; empty while it has no message yet."""
        return self._session.display_title() if self._session.messages else ""

    def rename(self, identifier: str, title: str) -> bool:
        """Rename a conversation of this project, the open one or a past one."""
        if identifier == self.session_identifier:
            session = self._session
        else:
            session = self._store.load(identifier)
            if session is None or session.project != self.project_key:
                return False
        if not session.rename(title):
            return False
        self._store.save(session)
        return True

    def delete(self, identifier: str) -> bool:
        """Delete a conversation of this project for good; the open one gives way to a fresh one.

        Returns whether the open conversation was the one deleted.
        """
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

    def recent(self) -> list[tuple[str, str, float, bool]]:
        """The project's conversations, newest first: identifier, title, when it last changed, whether it is open."""
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
