import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm import anthropic
from qgis_ai_agent.core.llm.anthropic_stream import AnthropicExchange
from qgis_ai_agent.core.llm.client import (
    ApiResponseError,
    build_request,
    post_chat_completion,
    resolve_endpoint,
)
from qgis_ai_agent.core.llm.dialects import ANTHROPIC, resolve
from qgis_ai_agent.core.llm.images import IMAGE_REJECTED_STATUS_CODES, has_images, without_images
from qgis_ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from qgis_ai_agent.core.llm.refusals import streaming_unsupported, thinking_unsupported, tools_unsupported
from qgis_ai_agent.core.llm.stream import StreamedCompletion, first_reasoning
from qgis_ai_agent.core.llm.stream_runner import post_stream
from qgis_ai_agent.core.llm.thinking import split_thinking
from qgis_ai_agent.core.settings import (
    get_dialect,
    get_supports_streaming,
    get_supports_thinking,
    get_supports_tools,
    get_thinking_budget,
    set_supports_images,
    set_supports_streaming,
    set_supports_thinking,
    set_supports_tools,
)

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


def parse_usage(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    incoming = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    outgoing = usage.get("completion_tokens", usage.get("output_tokens", 0))
    try:
        return int(incoming or 0), int(outgoing or 0)
    except (TypeError, ValueError):
        return 0, 0


def call_model(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
    timeout: int = 120,
    on_chunk: Any = None,
    on_thinking: Any = None,
) -> ModelTurn:
    overrides = dict(overrides or {})
    url = resolve_endpoint(overrides.get("url_override"))
    try:
        return _dispatch(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking)
    except ApiResponseError as err:
        if not (has_images(messages) and err.status_code in IMAGE_REJECTED_STATUS_CODES):
            raise
        turn = _dispatch(without_images(messages), tool_schemas, overrides, timeout, url, on_chunk, on_thinking)
        set_supports_images(url, False)
        return turn


def _dispatch(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
    on_chunk: Any = None,
    on_thinking: Any = None,
) -> ModelTurn:
    chosen = overrides.get("dialect_override")
    if resolve(url, chosen if chosen is not None else get_dialect()) == ANTHROPIC:
        return _call_anthropic(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking)
    supports_tools = get_supports_tools(url)

    if supports_tools is not False and tool_schemas:
        streamed = _try_streaming(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking)
        if streamed is not None:
            return streamed
        try:
            data = post_chat_completion(
                messages,
                extra_body={"tools": tool_schemas, "tool_choice": "auto"},
                timeout=timeout,
                **overrides,
            )
        except ApiResponseError as err:
            if not tools_unsupported(err):
                raise
            set_supports_tools(url, False)
        else:
            if supports_tools is None:
                set_supports_tools(url, True)
            return _parse_native_turn(data)

    return _parse_json_turn(post_chat_completion(messages, timeout=timeout, **overrides))


def _call_anthropic(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
    on_chunk: Any = None,
    on_thinking: Any = None,
) -> ModelTurn:
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
    )
    budget = get_thinking_budget() if get_supports_thinking(url) is not False else 0
    exchange = AnthropicExchange(endpoint, headers, timeout, url, overrides, on_chunk, on_thinking)
    try:
        data = exchange.send(anthropic.build_body(messages, tool_schemas, model, thinking_budget=budget))
    except ApiResponseError as err:
        if not budget or not thinking_unsupported(err):
            raise
        set_supports_thinking(url, False)
        data = exchange.send(anthropic.build_body(messages, tool_schemas, model))
    text, calls, stop_reason = anthropic.parse_response(data)
    thinking, thinking_blocks = anthropic.parse_thinking(data)
    incoming, outgoing = parse_usage(data)
    return ModelTurn(
        text=text,
        thinking=thinking,
        thinking_blocks=thinking_blocks,
        tool_calls=[
            ToolCall(
                id=call["id"] or f"call_{index}",
                name=call["name"],
                arguments=parse_tool_arguments(call["input"]),
            )
            for index, call in enumerate(calls)
            if call["name"]
        ],
        finish_reason=stop_reason,
        protocol=PROTOCOL_NATIVE,
        input_tokens=incoming,
        output_tokens=outgoing,
    )


def _try_streaming(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
    on_chunk: Any,
    on_thinking: Any = None,
) -> ModelTurn | None:
    if on_chunk is None or get_supports_streaming(url) is False:
        return None
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
    )
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": tool_schemas,
        "tool_choice": "auto",
    }
    try:
        completion = StreamedCompletion(on_chunk, on_thinking)
        data = post_stream(endpoint, headers, body, completion, timeout, overrides.get("verify_override"))
    except ApiResponseError as err:
        if streaming_unsupported(err):
            set_supports_streaming(url, False)
            return None
        raise
    turn = _parse_native_turn(data)
    if not turn.text and not turn.tool_calls:
        set_supports_streaming(url, False)
        return None
    if get_supports_streaming(url) is None:
        set_supports_streaming(url, True)
        set_supports_tools(url, True)
    return turn


def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("The API returned an empty answer.")
    return choices[0]


def _parse_native_turn(data: dict[str, Any]) -> ModelTurn:
    choice = _first_choice(data)
    message = choice.get("message") or {}
    incoming, outgoing = parse_usage(data)
    visible, inline_thinking = split_thinking(message.get("content") or "")
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


def _parse_json_turn(data: dict[str, Any]) -> ModelTurn:
    incoming, outgoing = parse_usage(data)
    message = _first_choice(data).get("message") or {}
    visible, inline_thinking = split_thinking(message.get("content") or "")
    content = visible.strip()
    thinking = _joined_thinking(message, inline_thinking)
    if not content:
        return ModelTurn(protocol=PROTOCOL_JSON, input_tokens=incoming, output_tokens=outgoing, thinking=thinking)
    try:
        parsed = parse_model_json(content)
    except json.JSONDecodeError:
        return ModelTurn(
            text=content,
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
            for call in (_json_call(index, raw) for index, raw in enumerate(parsed.get("tool_calls") or []))
            if call is not None
        ],
        protocol=PROTOCOL_JSON,
    )


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
