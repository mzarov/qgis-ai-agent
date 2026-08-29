import json
from collections.abc import Callable
from typing import Any

from qgis_ai_agent.core.llm.thinking import ThinkSplitter

DATA_PREFIX = "data:"
DONE_MARKER = "[DONE]"
EVENT_SEPARATOR = "\n"
REASONING_KEYS = ("reasoning_content", "reasoning")


def first_reasoning(payload: dict[str, Any]) -> str:
    for key in REASONING_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class SseAccumulator:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, raw: bytes) -> list[str]:
        self._buffer += raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        complete, separator, rest = self._buffer.rpartition(EVENT_SEPARATOR)
        if not separator:
            return []
        self._buffer = rest
        events = []
        for line in complete.split(EVENT_SEPARATOR):
            line = line.strip()
            if not line.startswith(DATA_PREFIX):
                continue
            payload = line[len(DATA_PREFIX) :].strip()
            if payload:
                events.append(payload)
        return events


class StreamedCompletion:
    def __init__(
        self,
        on_text: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
    ):
        self._on_text = on_text
        self._on_thinking = on_thinking
        self._text_parts: list[str] = []
        self._thinking_parts: list[str] = []
        self._splitter = ThinkSplitter()
        self._calls: dict[int, dict[str, Any]] = {}
        self._finish_reason = ""
        self._usage: dict[str, Any] = {}
        self.done = False

    def take(self, event: str) -> None:
        if event == DONE_MARKER:
            self.done = True
            return
        try:
            parsed = json.loads(event)
        except ValueError:
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
        text = delta.get("content")
        if isinstance(text, str) and text:
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
        index = int(raw.get("index") or 0)
        slot = self._calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if raw.get("id"):
            slot["id"] = str(raw["id"])
        function = raw.get("function") or {}
        if function.get("name"):
            slot["name"] += str(function["name"])
        if function.get("arguments"):
            slot["arguments"] += str(function["arguments"])

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


def consume(
    chunks: list[bytes],
    on_text: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    accumulator = SseAccumulator()
    completion = StreamedCompletion(on_text, on_thinking)
    for chunk in chunks:
        for event in accumulator.feed(chunk):
            completion.take(event)
    return completion.response()
