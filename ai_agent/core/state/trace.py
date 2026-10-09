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
CHOICE = "choice"
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
        self._steps: list[dict[str, Any]] = []
        self._open: dict[str, Any] | None = None
        self._thought: dict[str, Any] | None = None
        self._first = 0.0
        self._last = 0.0

    @property
    def pending(self) -> bool:
        return bool(self._steps)

    def call(self, summary: Any) -> None:
        """A call started; `summary` is its CallSummary (text, marked parts, skill)."""
        self._end_thought()
        step = {
            "kind": CALL,
            "text": str(summary),
            "parts": [[str(text), bool(marked)] for text, marked in getattr(summary, "parts", ())],
            "skill": str(getattr(summary, "skill", "") or ""),
            "ok": None,
            "note": "",
            "seconds": None,
        }
        self._add(step)
        self._open = step

    def finished(self, ok: bool, note: str = "") -> None:
        """The open call ended."""
        step = self._open
        if step is None:
            return
        step["ok"] = ok
        step["note"] = note
        step["seconds"] = round(self._clock() - step.pop("_started"), 2)
        self._last = self._clock()
        self._open = None

    def done(self, summary: Any) -> None:
        """A step that is over as it starts: a skill loaded, the plan moved on."""
        self.call(summary)
        if self._open is not None:
            self._open.pop("_started", None)
            self._open["ok"] = True
            self._open = None

    def rejected(self, summary: Any) -> None:
        self.done(summary)
        self._steps[-1].update(ok=False, rejected=True)

    def choice(self, answer: str) -> None:
        """The answer the user picked on a question card."""
        self._end_thought()
        self._add({"kind": CHOICE, "text": answer})

    def thinking(self, delta: str) -> None:
        if self._thought is None:
            self._thought = {"kind": THOUGHT, "text": "", "seconds": None, "_deliveries": 0}
            self._add(self._thought)
        self._thought["text"] += delta
        self._thought["_deliveries"] += 1

    def take(self) -> dict[str, Any] | None:
        """The turn's record, or None when nothing happened; the log starts afresh."""
        self._end_thought()
        if not self._steps:
            return None
        for step in self._steps:
            if step.pop("_started", None) is not None and step.get("ok") is None:
                # Cut short — a stop, an error: the replay shows it settled, without a time.
                step["seconds"] = None
        record = {"steps": self._steps, "seconds": round(max(0.0, self._last - self._first), 2)}
        self._steps, self._open, self._thought = [], None, None
        return record

    def drop(self) -> None:
        self._steps, self._open, self._thought = [], None, None

    def _add(self, step: dict[str, Any]) -> None:
        now = self._clock()
        if not self._steps:
            self._first = now
        step["_started"] = now
        self._steps.append(step)
        self._last = now

    def _end_thought(self) -> None:
        thought = self._thought
        if thought is None:
            return
        # Reasoning that came whole has no measurable duration; one that streamed has.
        started = thought.pop("_started", self._clock())
        if thought.pop("_deliveries", 0) > 1:
            thought["seconds"] = round(self._clock() - started, 2)
        self._last = self._clock()
        self._thought = None
