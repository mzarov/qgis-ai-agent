"""Noticing the same failure twice in one run, so the model changes course instead of retrying it.

A rule in the prompt was not enough: in the agent bench a model sent the same
failing export five times. The second identical failure now carries a note in its
result, which the model reads at the moment it decides the next call.
"""

from collections import Counter

from ai_agent.core.agent.transcript import ToolResult

REPEATED_KEY = "repeated"
NOTE_KEY = "note"
ERROR_KEY_CHARS = 300
REPEATED_NOTE = (
    "This is failure number {count} of {tool} with this same error in this request. "
    "Do not send it again unchanged: change the arguments or the approach, or tell the user what blocks you."
)


class FailureMemory:
    """Counts failures by tool and error within one run."""

    def __init__(self) -> None:
        self._seen: Counter[tuple[str, str]] = Counter()

    def reset(self) -> None:
        self._seen.clear()

    def note(self, result: ToolResult) -> ToolResult:
        """The result, with a note on its second and later identical failures; successes pass untouched."""
        if result.ok:
            return result
        error = str(result.payload.get("error") or "").strip()[:ERROR_KEY_CHARS]
        key = (result.call.name, error)
        self._seen[key] += 1
        count = self._seen[key]
        if count > 1:
            result.payload[REPEATED_KEY] = count
            result.payload[NOTE_KEY] = REPEATED_NOTE.format(count=count, tool=result.call.name)
        return result
