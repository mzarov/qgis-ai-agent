import time
from collections.abc import Callable
from typing import Any

TRACE_ROLE = "trace"
PLAN_ROLE = "plan"
CALL = "call"
THOUGHT = "thought"
PENDING = "pending"
APPLIED = "applied"
FAILED = "failed"
CANCELLED = "cancelled"
UNDONE = "undone"


class TraceLog:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.drop()

    def call(self, summary: Any) -> None:
        self._end_thought()
        self._open = {
            "kind": CALL,
            "text": str(summary),
            "parts": [[str(text), bool(marked)] for text, marked in getattr(summary, "parts", ())],
            "skill": str(getattr(summary, "skill", "") or ""),
            "ok": None,
            "note": "",
            "seconds": None,
        }
        self._opened = self._add(self._open)

    def finished(self, ok: bool, note: str = "") -> None:
        if self._open is None:
            return
        self._last = self._clock()
        self._open.update(ok=ok, note=note, seconds=round(self._last - self._opened, 2))
        self._open = None

    def done(self, summary: Any) -> None:
        self.call(summary)
        self._steps[-1]["ok"] = True
        self._open = None

    def rejected(self, summary: Any) -> None:
        self.done(summary)
        self._steps[-1].update(ok=False, rejected=True)

    def thinking(self, delta: str) -> None:
        if self._thought is None:
            self._thought = {"kind": THOUGHT, "text": "", "seconds": None}
            self._thought_started = self._add(self._thought)
            self._deliveries = 0
        self._thought["text"] += delta
        self._deliveries += 1

    def take(self) -> dict[str, Any] | None:
        self._end_thought()
        if not self._steps:
            return None
        record: dict[str, Any] = {"steps": self._steps, "seconds": round(max(0.0, self._last - self._first), 2)}
        if self.kind:
            record["kind"] = self.kind
        self.drop()
        return record

    def drop(self) -> None:
        self.kind = ""
        self._steps: list[dict[str, Any]] = []
        self._open: dict[str, Any] | None = None
        self._thought: dict[str, Any] | None = None
        self._opened = self._thought_started = self._first = self._last = 0.0
        self._deliveries = 0

    def _add(self, step: dict[str, Any]) -> float:
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
