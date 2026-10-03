import json
from dataclasses import dataclass, field
from typing import Any

from ai_agent.core.llm import anthropic
from ai_agent.core.llm.anthropic_stream import AnthropicExchange
from ai_agent.core.llm.client import (
    ApiResponseError,
    blocking_timeout,
    build_request,
    post_chat_completion,
    resolve_endpoint,
)
from ai_agent.core.llm.dialects import ANTHROPIC, ANTHROPIC_HOSTS, DEFAULT_MAX_TOKENS, host_of, resolve
from ai_agent.core.llm.images import IMAGE_REJECTED_STATUS_CODES, has_images, without_images
from ai_agent.core.llm.live import fold_live
from ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from ai_agent.core.llm.reasoning import is_deepseek, request_options, wire_messages
from ai_agent.core.llm.refusals import (
    may_reject_images,
    streaming_unsupported,
    thinking_unsupported,
    tools_unsupported,
)
from ai_agent.core.llm.retry import ChunkGuard, with_retries
from ai_agent.core.llm.stream import StreamedCompletion, first_reasoning
from ai_agent.core.llm.stream_runner import STREAM_EVENTS_KEY, post_stream
from ai_agent.core.llm.thinking import split_thinking
from ai_agent.core.settings import (
    get_dialect,
    get_model,
    get_reasoning_enabled,
    get_supports_streaming,
    get_supports_thinking,
    get_supports_tools,
    get_thinking_budget,
    get_verify_ssl,
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


ANTHROPIC_INPUT_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
JSON_TURN_KEYS = ("text", "message", "tool_calls")


def parse_usage(data: dict[str, Any]) -> tuple[int, int]:
    """Input and output tokens of one turn, counted the same way for both dialects.

    OpenAI's prompt_tokens already includes cached tokens; Anthropic's
    input_tokens does not, so the cache reads and writes are added back —
    otherwise the budget undercounts a cached run several times over.
    """
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
    if overrides.get("verify_override") is None:
        overrides["verify_override"] = get_verify_ssl(url)
    guard = ChunkGuard(on_chunk)
    chunks = guard if on_chunk is not None else None
    thoughts = guard.wrap(on_thinking)
    feedback = overrides.get("feedback_override")

    def attempt(payload: list[dict[str, Any]]) -> ModelTurn:
        return with_retries(
            lambda: _dispatch(payload, tool_schemas, overrides, timeout, url, chunks, thoughts),
            feedback,
            lambda: guard.delivered,
        )

    try:
        return attempt(messages)
    except ApiResponseError as err:
        if not (has_images(messages) and may_reject_images(err, IMAGE_REJECTED_STATUS_CODES)):
            raise
        turn = attempt(without_images(messages))
        cache_url, cache_model, cache_dialect = _capability_scope(url, overrides)
        set_supports_images(cache_url, False, cache_model, cache_dialect)
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
    cache_url, cache_model, cache_dialect = _capability_scope(url, overrides)
    if cache_dialect == ANTHROPIC:
        return _call_anthropic(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking)
    messages = fold_live(messages)
    reasoning = get_reasoning_enabled() and get_supports_thinking(cache_url, cache_model, cache_dialect) is not False
    try:
        return _call_openai(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking, reasoning)
    except ApiResponseError as err:
        if not (reasoning and thinking_unsupported(err)):
            raise
        set_supports_thinking(cache_url, False, cache_model, cache_dialect)
        return _call_openai(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking, False)


def _call_openai(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
    on_chunk: Any,
    on_thinking: Any,
    reasoning: bool,
) -> ModelTurn:
    cache_url, cache_model, cache_dialect = _capability_scope(url, overrides)
    messages = wire_messages(messages, url, reasoning)
    supports_tools = get_supports_tools(cache_url, cache_model, cache_dialect)

    if supports_tools is not False and tool_schemas:
        streamed = _try_streaming(messages, tool_schemas, overrides, timeout, url, on_chunk, on_thinking, reasoning)
        if streamed is not None:
            return streamed
        try:
            data = post_chat_completion(
                messages,
                extra_body=_openai_options(url, tool_schemas, reasoning),
                timeout=blocking_timeout(timeout),
                **overrides,
            )
        except ApiResponseError as err:
            if not tools_unsupported(err) or _refuses_reasoning(err, reasoning):
                raise
            set_supports_tools(cache_url, False, cache_model, cache_dialect)
        else:
            if supports_tools is None:
                set_supports_tools(cache_url, True, cache_model, cache_dialect)
            return _parse_native_turn(data)

    return _parse_json_turn(
        post_chat_completion(
            messages,
            extra_body=_openai_options(url, reasoning=reasoning),
            timeout=blocking_timeout(timeout),
            **overrides,
        )
    )


def _refuses_reasoning(err: ApiResponseError, reasoning: bool) -> bool:
    """A reasoning complaint must reach _dispatch, not be taken for a tools or streaming refusal."""
    return reasoning and thinking_unsupported(err)


def _call_anthropic(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any],
    timeout: int,
    url: str,
    on_chunk: Any = None,
    on_thinking: Any = None,
) -> ModelTurn:
    cache_url, cache_model, cache_dialect = _capability_scope(url, overrides)
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
    )
    budget = get_thinking_budget() if get_supports_thinking(cache_url, cache_model, cache_dialect) is not False else 0
    bind = anthropic.binds_thinking(model) and host_of(url) in ANTHROPIC_HOSTS
    if bind:
        headers = _with_beta(headers, anthropic.BINDING_BETA)
    exchange = AnthropicExchange(endpoint, headers, timeout, url, overrides, on_chunk, on_thinking)
    prefix = int(overrides.get(anthropic.CACHE_PREFIX_KEY) or 0)

    def body(thinking_budget: int, max_tokens: int = DEFAULT_MAX_TOKENS) -> dict[str, Any]:
        return anthropic.build_body(
            messages,
            tool_schemas,
            model,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            cache_prefix_chars=prefix,
            bind_thinking=bind,
        )

    try:
        data = exchange.send(body(budget))
    except ApiResponseError as err:
        if _asks_for_fewer_tokens(err):
            data = exchange.send(body(budget, anthropic.FALLBACK_MAX_TOKENS))
        elif budget and thinking_unsupported(err):
            set_supports_thinking(cache_url, False, cache_model, cache_dialect)
            data = exchange.send(body(0))
        else:
            raise
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
    reasoning: bool = False,
) -> ModelTurn | None:
    cache_url, cache_model, cache_dialect = _capability_scope(url, overrides)
    if on_chunk is None or get_supports_streaming(cache_url, cache_model, cache_dialect) is False:
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
    }
    body.update(_openai_options(url, tool_schemas, reasoning))
    try:
        completion = StreamedCompletion(on_chunk, on_thinking)
        stream_options = {}
        if overrides.get("feedback_override") is not None:
            stream_options["feedback"] = overrides["feedback_override"]
        data = post_stream(
            endpoint,
            headers,
            body,
            completion,
            timeout,
            overrides.get("verify_override"),
            **stream_options,
        )
    except ApiResponseError as err:
        if streaming_unsupported(err) and not _refuses_reasoning(err, reasoning):
            set_supports_streaming(cache_url, False, cache_model, cache_dialect)
            return None
        raise
    turn = _parse_native_turn(data)
    if data.get(STREAM_EVENTS_KEY) == 0:
        set_supports_streaming(cache_url, False, cache_model, cache_dialect)
        if not turn.text and not turn.tool_calls:
            return None
        return turn
    if get_supports_streaming(cache_url, cache_model, cache_dialect) is None:
        set_supports_streaming(cache_url, True, cache_model, cache_dialect)
        set_supports_tools(cache_url, True, cache_model, cache_dialect)
    return turn


def _with_beta(headers: dict[str, str], beta: str) -> dict[str, str]:
    merged = dict(headers)
    existing = [item.strip() for item in merged.get("anthropic-beta", "").split(",") if item.strip()]
    if beta not in existing:
        existing.append(beta)
    merged["anthropic-beta"] = ",".join(existing)
    return merged


def _asks_for_fewer_tokens(err: ApiResponseError) -> bool:
    body = (err.body or "").lower()
    return err.status_code == 400 and "max_tokens" in body and "thinking" not in body


def _capability_scope(url: str, overrides: dict[str, Any]) -> tuple[str, str, str]:
    chosen = overrides.get("dialect_override")
    dialect = resolve(url, chosen if chosen is not None else get_dialect())
    overridden_model = overrides.get("model_override")
    model = (overridden_model if overridden_model is not None else get_model()) or ""
    return url, model, dialect


def _openai_options(
    url: str,
    tool_schemas: list[dict[str, Any]] | None = None,
    reasoning: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if tool_schemas:
        body["tools"] = tool_schemas
    if tool_schemas and not is_deepseek(url):
        body["tool_choice"] = "auto"
    body.update(request_options(url, reasoning))
    return body


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
        parsed = {}
    if not isinstance(parsed, dict) or not any(key in parsed for key in JSON_TURN_KEYS):
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
            for call in (_json_call(index, raw) for index, raw in enumerate(_as_call_list(parsed.get("tool_calls"))))
            if call is not None
        ],
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
