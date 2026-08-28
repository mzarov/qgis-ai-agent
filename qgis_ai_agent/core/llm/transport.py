import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm import anthropic
from qgis_ai_agent.core.llm.client import (
    ApiResponseError,
    build_request,
    post_chat_completion,
    post_json,
    resolve_endpoint,
)
from qgis_ai_agent.core.llm.dialects import ANTHROPIC, resolve
from qgis_ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from qgis_ai_agent.core.settings import (
    get_dialect,
    get_supports_tools,
    set_supports_images,
    set_supports_tools,
)

PROTOCOL_NATIVE = "native"
PROTOCOL_JSON = "json"
UNSUPPORTED_STATUS_CODES = (400, 404, 422, 501)
IMAGE_REJECTED_STATUS_CODES = (400, 413, 415, 422)
IMAGE_URL_BLOCK = "image_url"
IMAGE_STRIPPED_NOTE = "[image omitted: this endpoint rejected image input]"
UNSUPPORTED_MARKERS = (
    "tools",
    "tool_choice",
    "function",
    "unsupported",
    "unrecognized",
    "unknown field",
    "not supported",
)


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
) -> ModelTurn:
    overrides = dict(overrides or {})
    url = resolve_endpoint(overrides.get("url_override"))
    try:
        return _dispatch(messages, tool_schemas, overrides, timeout, url)
    except ApiResponseError as err:
        if not (_has_images(messages) and err.status_code in IMAGE_REJECTED_STATUS_CODES):
            raise
        turn = _dispatch(_without_images(messages), tool_schemas, overrides, timeout, url)
        set_supports_images(url, False)
        return turn


def _has_images(messages: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(block, dict) and block.get("type") == IMAGE_URL_BLOCK
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
    )


def _without_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            cleaned.append(message)
            continue
        parts = [
            str(block.get("text") or "") if block.get("type") != IMAGE_URL_BLOCK else IMAGE_STRIPPED_NOTE
            for block in content
            if isinstance(block, dict)
        ]
        cleaned.append({**message, "content": "\n".join(part for part in parts if part)})
    return cleaned


def _dispatch(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
) -> ModelTurn:
    chosen = overrides.get("dialect_override")
    if resolve(url, chosen if chosen is not None else get_dialect()) == ANTHROPIC:
        return _call_anthropic(messages, tool_schemas, overrides, timeout)
    supports_tools = get_supports_tools(url)

    if supports_tools is not False and tool_schemas:
        try:
            data = post_chat_completion(
                messages,
                extra_body={"tools": tool_schemas, "tool_choice": "auto"},
                timeout=timeout,
                **overrides,
            )
        except ApiResponseError as err:
            if not _looks_like_tools_unsupported(err):
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
) -> ModelTurn:
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
    )
    body = anthropic.build_body(messages, tool_schemas, model)
    data = post_json(endpoint, headers, body, timeout, overrides.get("verify_override"))
    text, calls, stop_reason = anthropic.parse_response(data)
    incoming, outgoing = parse_usage(data)
    return ModelTurn(
        text=text,
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


def _looks_like_tools_unsupported(err: ApiResponseError) -> bool:
    if err.status_code not in UNSUPPORTED_STATUS_CODES:
        return False
    body = (err.body or "").lower()
    return any(marker in body for marker in UNSUPPORTED_MARKERS)


def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("The API returned an empty answer.")
    return choices[0]


def _parse_native_turn(data: dict[str, Any]) -> ModelTurn:
    choice = _first_choice(data)
    message = choice.get("message") or {}
    incoming, outgoing = parse_usage(data)
    return ModelTurn(
        input_tokens=incoming,
        output_tokens=outgoing,
        text=(message.get("content") or "").strip(),
        tool_calls=[
            call
            for call in (_native_call(index, raw) for index, raw in enumerate(message.get("tool_calls") or []))
            if call is not None
        ],
        finish_reason=(choice.get("finish_reason") or "").strip(),
        protocol=PROTOCOL_NATIVE,
    )


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
    content = ((_first_choice(data).get("message") or {}).get("content") or "").strip()
    if not content:
        return ModelTurn(protocol=PROTOCOL_JSON, input_tokens=incoming, output_tokens=outgoing)
    try:
        parsed = parse_model_json(content)
    except json.JSONDecodeError:
        return ModelTurn(text=content, protocol=PROTOCOL_JSON, input_tokens=incoming, output_tokens=outgoing)

    return ModelTurn(
        input_tokens=incoming,
        output_tokens=outgoing,
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
