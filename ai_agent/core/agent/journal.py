import html
import os
import tempfile
import time
import unicodedata
import uuid
from collections.abc import Sequence
from typing import Any

from ai_agent.core.agent.transcript import StepOutcome, ToolResult, TranscriptEntry

FOLDER = "ai_agent_runs"
JOURNAL_PREFIX = "run_"
OK_MARK = "[ok]"
FAIL_MARK = "[failed]"
DEDUPLICATED_MARK = "[deduplicated]"
MAX_TEXT_CHARS = 400
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
MARKDOWN_PUNCTUATION = "\\`*_{}[]()#+!|~"


def record_run(
    prompt: str,
    entries: Sequence[TranscriptEntry],
    outcome: str,
    applied: int,
    requests: Sequence[tuple[int, int, float]] = (),
) -> str:
    return write_journal(render_journal(prompt, entries, outcome, applied, requests))


def render_journal(
    prompt: str,
    entries: Sequence[TranscriptEntry],
    outcome: str,
    applied: int,
    requests: Sequence[tuple[int, int, float]] = (),
) -> str:
    lines = ["# Run journal", "", f"**Request:** {_safe_text(prompt)}", ""]
    for entry in entries:
        lines.extend(_entry_lines(entry))
    lines.extend(["", f"**Applied steps:** {applied}", "", f"**Outcome:** {_safe_text(outcome)}"])
    lines.extend(_request_lines(requests))
    return "\n".join(lines)


def _request_lines(requests: Sequence[tuple[int, int, float]]) -> list[str]:
    if not requests:
        return []
    lines = ["", "## Model requests", "", "| # | input tokens | output tokens | seconds |", "| --- | --- | --- | --- |"]
    for index, (prompt, completion, seconds) in enumerate(requests, start=1):
        lines.append(f"| {index} | {prompt} | {completion} | {seconds:.1f} |")
    prompt_total = sum(item[0] for item in requests)
    completion_total = sum(item[1] for item in requests)
    seconds_total = sum(item[2] for item in requests)
    lines.extend(
        [
            "",
            f"**Total:** {len(requests)} requests, {prompt_total} input and {completion_total} output tokens, "
            f"{seconds_total:.1f} s waiting for the model",
        ]
    )
    return lines


def write_journal(markdown: str, folder: str | None = None) -> str:
    target = os.path.abspath(os.path.expanduser(folder or default_root()))
    _ensure_private_directory(target)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(target, f"{JOURNAL_PREFIX}{stamp}_{uuid.uuid4().hex}.md")
    descriptor, temporary = tempfile.mkstemp(prefix=".run-", suffix=".tmp", dir=target)
    try:
        _set_descriptor_mode(descriptor, temporary)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(markdown.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_folder(target)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return path


def usage() -> tuple[int, int]:
    paths = _journals()
    size = 0
    for path in paths:
        try:
            size += os.path.getsize(path)
        except OSError:
            continue
    return len(paths), size


def erase() -> None:
    for path in _journals():
        try:
            os.remove(path)
        except OSError:
            continue


def _journals() -> list[str]:
    target = os.path.abspath(os.path.expanduser(default_root()))
    try:
        names = os.listdir(target)
    except OSError:
        return []
    return [os.path.join(target, name) for name in names if name.startswith(JOURNAL_PREFIX) and name.endswith(".md")]


def default_root() -> str:
    try:
        from qgis.core import QgsApplication

        base = QgsApplication.qgisSettingsDirPath()
    except Exception:
        base = ""
    if not isinstance(base, str) or not base:
        base = os.path.expanduser("~")
    return os.path.join(base, FOLDER)


def _ensure_private_directory(path: str) -> None:
    if os.path.islink(path):
        raise OSError("Journal directory must not be a symbolic link.")
    os.makedirs(path, mode=DIRECTORY_MODE, exist_ok=True)
    if not os.path.isdir(path):
        raise OSError("Journal location is not a directory.")
    os.chmod(path, DIRECTORY_MODE)


def _set_descriptor_mode(descriptor: int, path: str) -> None:
    try:
        os.fchmod(descriptor, FILE_MODE)
    except (AttributeError, OSError):
        os.chmod(path, FILE_MODE)


def _sync_folder(folder: str) -> None:
    try:
        descriptor = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _entry_lines(entry: TranscriptEntry) -> list[str]:
    if entry["kind"] == "user":
        return [f"- **user:** {_safe_text(entry.get('text', ''))}"]
    if entry["kind"] == "turn":
        turn = entry["turn"]
        lines = []
        if turn.text.strip():
            lines.append(f"- **agent:** {_safe_text(turn.text)}")
        for call in turn.tool_calls:
            lines.append(f"- call `{_safe_identifier(call.name)}`")
        return lines
    if entry["kind"] == "results":
        return [_result_line(result) for result in entry.get("results", [])]
    return []


def _result_line(result: ToolResult) -> str:
    name = _safe_identifier(result.call.name)
    if result.outcome is StepOutcome.DEDUPLICATED:
        return f"  - `{name}` {DEDUPLICATED_MARK}"
    mark = OK_MARK if result.ok else FAIL_MARK
    error = f" — {_safe_text(result.error)}" if not result.ok else ""
    return f"  - `{name}` {mark}{error}"


def _shortened(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= MAX_TEXT_CHARS else flat[:MAX_TEXT_CHARS] + "…"


def _safe_text(text: Any) -> str:
    cleaned = "".join(_visible_character(character) for character in _shortened(str(text or "")))
    escaped = html.escape(cleaned, quote=False).replace("\\", "\\\\")
    for character in MARKDOWN_PUNCTUATION[1:]:
        escaped = escaped.replace(character, "\\" + character)
    return escaped


def _visible_character(character: str) -> str:
    return f"\\u{ord(character):04x}" if unicodedata.category(character) in {"Cc", "Cf"} else character


def _safe_identifier(value: Any) -> str:
    return "".join(
        character if character.isascii() and (character.isalnum() or character in "_.-") else f"\\u{ord(character):04x}"
        for character in _shortened(str(value or ""))
    )
