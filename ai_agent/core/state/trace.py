import time
from collections.abc import Callable
from typing import NotRequired, TypedDict

TRACE_ROLE = "trace"
PLAN_ROLE = "plan"
CALL = "call"
THOUGHT = "thought"
PENDING = "pending"
APPLIED = "applied"
FAILED = "failed"
CANCELLED = "cancelled"
UNDONE = "undone"


class CallStep(TypedDict):
    kind: str
    text: str
    parts: list[list[str | bool]]
    skill: str
    ok: bool | None
    note: str
    seconds: float | None
    rejected: NotRequired[bool]


class ThoughtStep(TypedDict):
    kind: str
    text: str
    seconds: float | None


class TraceRecord(TypedDict):
    steps: list[CallStep | ThoughtStep]
    seconds: float
    kind: NotRequired[str]


class TraceLog:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.kind = ""
        self._steps: list[CallStep | ThoughtStep] = []
        self._open: CallStep | None = None
        self._thought: ThoughtStep | None = None
        self._opened = self._thought_started = self._first = self._last = 0.0
        self._deliveries = 0

    def call(self, summary: str) -> None:
        self._call(summary)

    def finished(self, ok: bool, note: str = "") -> None:
        if self._open is None:
            return
        self._last = self._clock()
        self._open["ok"] = ok
        self._open["note"] = note
        self._open["seconds"] = round(self._last - self._opened, 2)
        self._open = None

    def done(self, summary: str) -> None:
        self._settled(summary)

    def rejected(self, summary: str) -> None:
        step = self._settled(summary)
        step["ok"] = False
        step["rejected"] = True

    def thinking(self, delta: str) -> None:
        if self._thought is None:
            self._thought = {"kind": THOUGHT, "text": "", "seconds": None}
            self._thought_started = self._add(self._thought)
            self._deliveries = 0
        self._thought["text"] += delta
        self._deliveries += 1

    def take(self) -> TraceRecord | None:
        self._end_thought()
        if not self._steps:
            return None
        record: TraceRecord = {"steps": self._steps, "seconds": round(max(0.0, self._last - self._first), 2)}
        if self.kind:
            record["kind"] = self.kind
        self.drop()
        return record

    def drop(self) -> None:
        self.kind = ""
        self._steps = []
        self._open = None
        self._thought = None
        self._opened = self._thought_started = self._first = self._last = 0.0
        self._deliveries = 0

    def _call(self, summary: str) -> CallStep:
        self._end_thought()
        step: CallStep = {
            "kind": CALL,
            "text": str(summary),
            "parts": [[str(text), bool(marked)] for text, marked in getattr(summary, "parts", ())],
            "skill": str(getattr(summary, "skill", "") or ""),
            "ok": None,
            "note": "",
            "seconds": None,
        }
        self._open = step
        self._opened = self._add(step)
        return step

    def _settled(self, summary: str) -> CallStep:
        step = self._call(summary)
        step["ok"] = True
        self._open = None
        return step

    def _add(self, step: CallStep | ThoughtStep) -> float:
        now = self._clock()
        if not self._steps:
            self._first = now
        self._steps.append(step)
        self._last = now
        return now

    def _end_thought(self) -> None:
        if self._thought is None:
            return
        self._last = self._clock()
        if self._deliveries > 1:
            self._thought["seconds"] = round(self._last - self._thought_started, 2)
        self._thought = None
