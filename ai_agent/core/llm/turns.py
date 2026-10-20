import json
from dataclasses import dataclass, field
from typing import Any

from ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from ai_agent.core.llm.stream import first_reasoning, split_content
from ai_agent.core.llm.thinking import split_thinking

PROTOCOL_NATIVE = "native"
PROTOCOL_JSON = "json"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    protocol: str = PROTOCOL_NATIVE
    input_tokens: int = 0
    output_tokens: int = 0
    thinking: str = ""
    thinking_blocks: list[dict[str, Any]] = field(default_factory=list)


ANTHROPIC_INPUT_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
JSON_TURN_KEYS = ("text", "message", "tool_calls")


def parse_usage(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    outgoing = usage.get("completion_tokens", usage.get("output_tokens", 0))
    try:
        if "prompt_tokens" in usage:
            incoming = int(usage.get("prompt_tokens") or 0)
        else:
            incoming = sum(int(usage.get(key) or 0) for key in ANTHROPIC_INPUT_KEYS)
        return incoming, int(outgoing or 0)
    except (TypeError, ValueError):
        return 0, 0


def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("The API returned an empty answer.")
    choice: dict[str, Any] = choices[0]
    return choice


def parse_native_turn(data: dict[str, Any]) -> ModelTurn:
    choice = _first_choice(data)
    message = choice.get("message") or {}
    incoming, outgoing = parse_usage(data)
    visible, inline_thinking = _split_message(message)
    return ModelTurn(
        input_tokens=incoming,
        output_tokens=outgoing,
        thinking=_joined_thinking(message, inline_thinking),
        text=visible.strip(),
        tool_calls=[
            call
            for call in (_native_call(index, raw) for index, raw in enumerate(message.get("tool_calls") or []))
            if call is not None
        ],
        finish_reason=(choice.get("finish_reason") or "").strip(),
        protocol=PROTOCOL_NATIVE,
    )


def _split_message(message: dict[str, Any]) -> tuple[str, str]:
    text, listed_thinking = split_content(message.get("content"))
    visible, inline_thinking = split_thinking(text)
    return visible, listed_thinking + inline_thinking


def _joined_thinking(message: dict[str, Any], inline: str) -> str:
    parts = [first_reasoning(message), inline]
    return "\n".join(part.strip() for part in parts if part.strip())


def _native_call(index: int, raw: dict[str, Any]) -> ToolCall | None:
    function = raw.get("function") or {}
    name = (function.get("name") or "").strip()
    if not name:
        return None
    return ToolCall(
        id=raw.get("id") or f"call_{index}",
        name=name,
        arguments=parse_tool_arguments(function.get("arguments")),
    )


def parse_json_turn(data: dict[str, Any]) -> ModelTurn:
    incoming, outgoing = parse_usage(data)
    choice = _first_choice(data)
    message = choice.get("message") or {}
    finish_reason = (choice.get("finish_reason") or "").strip()
    visible, inline_thinking = _split_message(message)
    content = visible.strip()
    thinking = _joined_thinking(message, inline_thinking)
    if not content:
        return ModelTurn(
            finish_reason=finish_reason,
            protocol=PROTOCOL_JSON,
            input_tokens=incoming,
            output_tokens=outgoing,
            thinking=thinking,
        )
    try:
        parsed = parse_model_json(content)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict) or not any(key in parsed for key in JSON_TURN_KEYS):
        return ModelTurn(
            text=content,
            finish_reason=finish_reason,
            protocol=PROTOCOL_JSON,
            input_tokens=incoming,
            output_tokens=outgoing,
            thinking=thinking,
        )

    return ModelTurn(
        input_tokens=incoming,
        output_tokens=outgoing,
        thinking=thinking,
        text=(parsed.get("text") or parsed.get("message") or "").strip(),
        tool_calls=[
            call
            for call in (_json_call(index, raw) for index, raw in enumerate(_as_call_list(parsed.get("tool_calls"))))
            if call is not None
        ],
        finish_reason=finish_reason,
        protocol=PROTOCOL_JSON,
    )


def _as_call_list(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        return [raw]
    return raw if isinstance(raw, list) else []


def _json_call(index: int, raw: Any) -> ToolCall | None:
    if not isinstance(raw, dict):
        return None
    name = (raw.get("name") or raw.get("tool") or "").strip()
    if not name:
        return None
    raw_arguments = raw.get("arguments") if "arguments" in raw else raw.get("params")
    return ToolCall(
        id=raw.get("id") or f"call_{index}",
        name=name,
        arguments=parse_tool_arguments(raw_arguments),
    )
