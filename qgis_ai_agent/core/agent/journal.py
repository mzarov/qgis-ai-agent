import os
import tempfile
import time
from typing import Any

FOLDER = "qgis_ai_agent_runs"
OK_MARK = "[ok]"
FAIL_MARK = "[failed]"
MAX_TEXT_CHARS = 400


def record_run(prompt: str, entries: list[dict[str, Any]], outcome: str, applied: int) -> str:
    return write_journal(render_journal(prompt, entries, outcome, applied))


def render_journal(prompt: str, entries: list[dict[str, Any]], outcome: str, applied: int) -> str:
    lines = ["# Run journal", "", f"**Request:** {_shortened(prompt)}", ""]
    for entry in entries:
        lines.extend(_entry_lines(entry))
    lines.extend(["", f"**Applied steps:** {applied}", "", f"**Outcome:** {_shortened(outcome)}"])
    return "\n".join(lines)


def write_journal(markdown: str, folder: str | None = None) -> str:
    target = folder or os.path.join(tempfile.gettempdir(), FOLDER)
    os.makedirs(target, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(target, f"run_{stamp}.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    return path


def _entry_lines(entry: dict[str, Any]) -> list[str]:
    kind = entry.get("kind")
    if kind == "user":
        return [f"- **user:** {_shortened(entry.get('text', ''))}"]
    if kind == "turn":
        turn = entry["turn"]
        lines = []
        if turn.text.strip():
            lines.append(f"- **agent:** {_shortened(turn.text)}")
        for call in turn.tool_calls:
            lines.append(f"- call `{call.name}`")
        return lines
    if kind == "results":
        return [
            f"  - `{result.call.name}` {OK_MARK if result.ok else FAIL_MARK}"
            + (f" — {_shortened(str(result.payload.get('error', '')))}" if not result.ok else "")
            for result in entry.get("results", [])
        ]
    return []


def _shortened(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= MAX_TEXT_CHARS else flat[:MAX_TEXT_CHARS] + "…"
