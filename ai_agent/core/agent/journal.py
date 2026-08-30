import html
import os
import tempfile
import time
import unicodedata
import uuid
from typing import Any

FOLDER = "ai_agent_runs"
OK_MARK = "[ok]"
FAIL_MARK = "[failed]"
DEDUPLICATED_MARK = "[deduplicated]"
MAX_TEXT_CHARS = 400
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
MARKDOWN_PUNCTUATION = "\\`*_{}[]()#+!|~"


def record_run(prompt: str, entries: list[dict[str, Any]], outcome: str, applied: int) -> str:
    return write_journal(render_journal(prompt, entries, outcome, applied))


def render_journal(prompt: str, entries: list[dict[str, Any]], outcome: str, applied: int) -> str:
    lines = ["# Run journal", "", f"**Request:** {_safe_text(prompt)}", ""]
    for entry in entries:
        lines.extend(_entry_lines(entry))
    lines.extend(["", f"**Applied steps:** {applied}", "", f"**Outcome:** {_safe_text(outcome)}"])
    return "\n".join(lines)


def write_journal(markdown: str, folder: str | None = None) -> str:
    target = os.path.abspath(os.path.expanduser(folder or default_root()))
    _ensure_private_directory(target)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(target, f"run_{stamp}_{uuid.uuid4().hex}.md")
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


def _entry_lines(entry: dict[str, Any]) -> list[str]:
    kind = entry.get("kind")
    if kind == "user":
        return [f"- **user:** {_safe_text(entry.get('text', ''))}"]
    if kind == "turn":
        turn = entry["turn"]
        lines = []
        if turn.text.strip():
            lines.append(f"- **agent:** {_safe_text(turn.text)}")
        for call in turn.tool_calls:
            lines.append(f"- call `{_safe_identifier(call.name)}`")
        return lines
    if kind == "results":
        return [_result_line(result) for result in entry.get("results", [])]
    return []


def _result_line(result: Any) -> str:
    name = _safe_identifier(result.call.name)
    if result.payload.get("deduplicated") is True:
        return f"  - `{name}` {DEDUPLICATED_MARK}"
    mark = OK_MARK if result.ok else FAIL_MARK
    error = f" — {_safe_text(result.payload.get('error', ''))}" if not result.ok else ""
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
