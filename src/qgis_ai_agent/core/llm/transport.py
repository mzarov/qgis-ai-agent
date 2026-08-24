import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm.client import (
    ApiResponseError,
    post_chat_completion,
    resolve_endpoint,
)
from qgis_ai_agent.core.llm.parser import parse_model_json, parse_tool_arguments
from qgis_ai_agent.core.settings import get_supports_tools, set_supports_tools

# Признаки того, что эндпоинт не понимает параметр tools.
_UNSUPPORTED_MARKERS = (
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
    """Один вызов тула, запрошенный моделью."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    """Нормализованный ход модели: текст плюс запрошенные вызовы тулов."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    # Каким протоколом получен ход: native (tool_calls API) или json (фолбэк).
    protocol: str = "native"


def call_model(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
    timeout: int = 120,
) -> ModelTurn:
    """
    Запрашивает следующий ход модели.
    Сначала пробует нативный function calling, при отказе эндпоинта
    переключается на JSON-протокол в промпте и запоминает выбор.
    """
    overrides = dict(overrides or {})
    url = resolve_endpoint(overrides.get("url_override"))
    supports_tools = get_supports_tools(url)

    if supports_tools is not False and tool_schemas:
        try:
            data = post_chat_completion(
                messages,
                extra_body={"tools": tool_schemas, "tool_choice": "auto"},
                timeout=timeout,
                **overrides,
            )
            if supports_tools is None:
                set_supports_tools(url, True)
            return _parse_native_turn(data)
        except ApiResponseError as err:
            if not _looks_like_tools_unsupported(err):
                raise
            set_supports_tools(url, False)

    data = post_chat_completion(messages, timeout=timeout, **overrides)
    return _parse_json_turn(data)


def _looks_like_tools_unsupported(err: ApiResponseError) -> bool:
    """Отличает отказ из-за неподдержки tools от прочих ошибок API."""
    if err.status_code not in (400, 404, 422, 501):
        return False
    body = (err.body or "").lower()
    return any(marker in body for marker in _UNSUPPORTED_MARKERS)


def _first_message(data: dict[str, Any]) -> dict[str, Any]:
    """Достаёт message из первого choice ответа API."""
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Пустой ответ API.")
    return choices[0].get("message") or {}


def _parse_native_turn(data: dict[str, Any]) -> ModelTurn:
    """Разбирает ответ с нативными tool_calls."""
    message = _first_message(data)
    choices = data.get("choices") or [{}]
    calls: list[ToolCall] = []
    for index, raw_call in enumerate(message.get("tool_calls") or []):
        function = raw_call.get("function") or {}
        name = (function.get("name") or "").strip()
        if not name:
            continue
        calls.append(
            ToolCall(
                id=raw_call.get("id") or f"call_{index}",
                name=name,
                arguments=parse_tool_arguments(function.get("arguments")),
            )
        )
    return ModelTurn(
        text=(message.get("content") or "").strip(),
        tool_calls=calls,
        finish_reason=(choices[0].get("finish_reason") or "").strip(),
        protocol="native",
    )


def _parse_json_turn(data: dict[str, Any]) -> ModelTurn:
    """Разбирает ответ JSON-протокола: {"text": ..., "tool_calls": [...]}."""
    message = _first_message(data)
    content = (message.get("content") or "").strip()
    if not content:
        return ModelTurn(text="", tool_calls=[], protocol="json")
    try:
        parsed = parse_model_json(content)
    except json.JSONDecodeError:
        # Модель ответила обычным текстом — считаем это финальным ответом.
        return ModelTurn(text=content, tool_calls=[], protocol="json")

    calls: list[ToolCall] = []
    for index, raw_call in enumerate(parsed.get("tool_calls") or []):
        if not isinstance(raw_call, dict):
            continue
        name = (raw_call.get("name") or raw_call.get("tool") or "").strip()
        if not name:
            continue
        calls.append(
            ToolCall(
                id=raw_call.get("id") or f"call_{index}",
                name=name,
                arguments=parse_tool_arguments(
                    raw_call.get("arguments") if "arguments" in raw_call else raw_call.get("params")
                ),
            )
        )
    return ModelTurn(
        text=(parsed.get("text") or parsed.get("message") or "").strip(),
        tool_calls=calls,
        protocol="json",
    )
