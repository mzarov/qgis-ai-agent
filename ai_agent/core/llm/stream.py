import json
from collections.abc import Callable
from typing import Any

from ai_agent.core.llm.thinking import ThinkSplitter, leading_close

DATA_PREFIX = "data:"
DONE_MARKER = "[DONE]"
SSE_FIELD_PREFIXES = ("event:", "id:", "retry:", ":")
REASONING_KEYS = ("reasoning_content", "reasoning")
THINKING_PART_TYPES = ("thinking", "reasoning")
TEXT_PART_TYPE = "text"


def first_reasoning(payload: dict[str, Any]) -> str:
    for key in REASONING_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def split_content(content: Any) -> tuple[str, str]:
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return "", ""
    text: list[str] = []
    thinking: list[str] = []
    for part in content:
        if isinstance(part, str):
            text.append(part)
        elif isinstance(part, dict) and part.get("type") in THINKING_PART_TYPES:
            thinking.append(_part_text(part.get(part["type"]) or part.get(TEXT_PART_TYPE)))
        elif isinstance(part, dict) and part.get("type", TEXT_PART_TYPE) == TEXT_PART_TYPE:
            text.append(_part_text(part.get(TEXT_PART_TYPE)))
    return "".join(text), "".join(thinking)


def _part_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_part_text(item.get(TEXT_PART_TYPE) if isinstance(item, dict) else item) for item in value)
    return ""


class SseAccumulator:
    def __init__(self) -> None:
        self._buffer = b""
        self._pending: list[str] = []
        self._plain: list[str] = []
        self.event_count = 0

    def feed(self, raw: bytes) -> list[str]:
        self._buffer += raw
        *lines, self._buffer = self._buffer.split(b"\n")
        events: list[str] = []
        for line in lines:
            self._take_line(line.rstrip(b"\r").decode("utf-8", errors="replace"), events)
        return events

    def flush(self) -> list[str]:
        events: list[str] = []
        if self._buffer:
            self._take_line(self._buffer.rstrip(b"\r").decode("utf-8", errors="replace"), events)
            self._buffer = b""
        self._emit_pending(events)
        return events

    def plain_json(self) -> Any:
        text = "\n".join(self._plain).strip()
        if not text or self.event_count:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def _take_line(self, line: str, events: list[str]) -> None:
        stripped = line.strip()
        if not stripped:
            self._emit_pending(events)
            return
        if stripped.startswith(DATA_PREFIX):
            payload = stripped[len(DATA_PREFIX) :].strip()
            if payload:
                self._pending.append(payload)
                if _complete(self._pending):
                    self._emit_pending(events)
            return
        if not stripped.startswith(SSE_FIELD_PREFIXES):
            self._plain.append(line)

    def _emit_pending(self, events: list[str]) -> None:
        if self._pending:
            events.append("\n".join(self._pending))
            self._pending = []
            self.event_count += 1


def _complete(pending: list[str]) -> bool:
    joined = "\n".join(pending)
    if joined == DONE_MARKER:
        return True
    try:
        json.loads(joined)
    except ValueError:
        return False
    return True


def _given_index(raw: dict[str, Any]) -> int | None:
    try:
        return int(raw["index"]) if raw.get("index") is not None else None
    except (TypeError, ValueError):
        return None


class StreamedCompletion:
    def __init__(
        self,
        on_text: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        held: bool = False,
    ):
        self._on_text = on_text
        self._on_thinking = on_thinking
        self._text_parts: list[str] = []
        self._thinking_parts: list[str] = []
        self._splitter = ThinkSplitter(held)
        self._calls: dict[int, dict[str, Any]] = {}
        self._moved: dict[int, int] = {}
        self._finish_reason = ""
        self._usage: dict[str, Any] = {}
        self._last_index = 0
        self.done = False
        self.error: dict[str, Any] | None = None

    @property
    def finished(self) -> bool:
        return self.done or bool(self._finish_reason)

    @property
    def closed_without_opening(self) -> bool:
        return self._splitter.closed_without_opening or bool(leading_close("".join(self._text_parts))[1])

    def take(self, event: str) -> None:
        if event == DONE_MARKER:
            self.done = True
            return
        try:
            parsed = json.loads(event)
        except ValueError:
            return
        if not isinstance(parsed, dict):
            return
        if isinstance(parsed.get("error"), (dict, str)):
            self.error = parsed["error"] if isinstance(parsed["error"], dict) else {"message": parsed["error"]}
            return
        usage = parsed.get("usage")
        if isinstance(usage, dict):
            self._usage = usage
        for choice in parsed.get("choices") or []:
            self._take_choice(choice)

    def _take_choice(self, choice: dict[str, Any]) -> None:
        reason = choice.get("finish_reason")
        if reason:
            self._finish_reason = str(reason)
        delta = choice.get("delta") or {}
        for raw_call in delta.get("tool_calls") or []:
            self._take_call(raw_call)
        reasoning = first_reasoning(delta)
        if reasoning:
            self._take_thinking(reasoning)
        text, listed_thought = split_content(delta.get("content"))
        if listed_thought:
            self._take_thinking(listed_thought)
        if text:
            visible, thought = self._splitter.feed(text)
            if thought:
                self._take_thinking(thought)
            if visible:
                self._text_parts.append(visible)
                if self._on_text is not None and not self._calls:
                    self._on_text(visible)

    def _take_thinking(self, text: str) -> None:
        self._thinking_parts.append(text)
        if self._on_thinking is not None:
            self._on_thinking(text)

    def _take_call(self, raw: dict[str, Any]) -> None:
        index = self._call_index(raw)
        self._last_index = index
        slot = self._calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if raw.get("id"):
            slot["id"] = str(raw["id"])
        function = raw.get("function") or {}
        name = str(function.get("name") or "")
        if name and slot["name"] != name:
            slot["name"] += name
        arguments = function.get("arguments")
        if isinstance(arguments, dict):
            slot["arguments"] += json.dumps(arguments, ensure_ascii=False)
        elif arguments:
            slot["arguments"] += str(arguments)

    def _call_index(self, raw: dict[str, Any]) -> int:
        given = _given_index(raw)
        index = self._last_index if given is None else self._moved.get(given, given)
        current = self._calls.get(index)
        new_id = str(raw.get("id") or "")
        # Ollama numbers every parallel call 0: a new id in an occupied slot is a new call.
        if current is not None and new_id and current["id"] and current["id"] != new_id:
            index = max(self._calls) + 1
            if given is not None:
                self._moved[given] = index
        return index

    def response(self) -> dict[str, Any]:
        visible, thought = self._splitter.flush()
        if thought:
            self._take_thinking(thought)
        if visible:
            self._text_parts.append(visible)
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text_parts)}
        if self._thinking_parts:
            message["reasoning_content"] = "".join(self._thinking_parts)
        if self._calls:
            message["tool_calls"] = [
                {
                    "id": slot["id"],
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["arguments"]},
                }
                for _, slot in sorted(self._calls.items())
            ]
        built: dict[str, Any] = {"choices": [{"message": message, "finish_reason": self._finish_reason}]}
        if self._usage:
            built["usage"] = self._usage
        return built
