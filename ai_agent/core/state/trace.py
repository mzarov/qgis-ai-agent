"""What a turn showed besides its messages — the steps, the reasoning, a plan card — kept for a reopened chat.

The model never gets any of it: the entries are display-only, saved beside the
messages under roles of their own (`TRACE_ROLE`, `PLAN_ROLE`) that the model's
window skips. `TraceLog` hears the same events the orchestrator draws — a call
started and finished, a skill loaded, reasoning streamed — and hands one turn's
steps over as a record just before the next message is written, so a replay draws
them where they were. Pure Python: the clock is injectable for tests.
"""

import time
from collections.abc import Callable
from typing import Any

TRACE_ROLE = "trace"
PLAN_ROLE = "plan"
CALL = "call"
THOUGHT = "thought"
# A plan card's ends, as the replay settles it.
PENDING = "pending"
APPLIED = "applied"
FAILED = "failed"
CANCELLED = "cancelled"
UNDONE = "undone"


class TraceLog:
    """One turn's steps as they happen; `take` hands them over and starts afresh."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.drop()

    def call(self, summary: Any) -> None:
        """A call started; `summary` is its CallSummary (text, marked parts, skill)."""
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
        """The open call ended."""
        if self._open is None:
            return
        self._last = self._clock()
        self._open.update(ok=ok, note=note, seconds=round(self._last - self._opened, 2))
        self._open = None

    def done(self, summary: Any) -> None:
        """A step that is over as it starts: a skill loaded, the plan moved on."""
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
        """The turn's record, or None when nothing happened; the log starts afresh.

        A call cut short — a stop, an error — keeps no time: the replay shows it settled.
        """
        self._end_thought()
        if not self._steps:
            return None
        record = {"steps": self._steps, "seconds": round(max(0.0, self._last - self._first), 2)}
        self.drop()
        return record

    def drop(self) -> None:
        self._steps: list[dict[str, Any]] = []
        self._open: dict[str, Any] | None = None
        self._thought: dict[str, Any] | None = None
        self._opened = self._thought_started = self._first = self._last = 0.0
        self._deliveries = 0

    def _add(self, step: dict[str, Any]) -> float:
        """Append a step; the time it started."""
        now = self._clock()
        if not self._steps:
            self._first = now
        self._steps.append(step)
        self._last = now
        return now

    def _end_thought(self) -> None:
        if self._thought is None:
            return
        # Reasoning that came whole has no measurable duration; one that streamed has.
        self._last = self._clock()
        if self._deliveries > 1:
            self._thought["seconds"] = round(self._last - self._thought_started, 2)
        self._thought = None
