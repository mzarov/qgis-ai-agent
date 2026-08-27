import json
from typing import Any

from qgis_ai_agent.core.llm.dialects import DEFAULT_MAX_TOKENS

TEXT_BLOCK = "text"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
USER = "user"
ASSISTANT = "assistant"
SYSTEM = "system"
TOOL = "tool"


def build_body(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]] | None,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    system, turns = split_system(messages)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": turns,
    }
    if system:
        body["system"] = system
    if tool_schemas:
        body["tools"] = [translate_tool(schema) for schema in tool_schemas]
    return body


def split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    preamble: list[str] = []
    turns: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == SYSTEM:
            preamble.append(str(message.get("content") or ""))
            continue
        translated = translate_message(message)
        if translated is not None:
            turns.append(translated)
    return "\n\n".join(part for part in preamble if part), _merged(turns)


def translate_message(message: dict[str, Any]) -> dict[str, Any] | None:
    role = message.get("role")
    if role == TOOL:
        return _result_message(message)
    if role == ASSISTANT:
        return _assistant_message(message)
    content = str(message.get("content") or "")
    return {"role": USER, "content": content} if content else None


def translate_tool(schema: dict[str, Any]) -> dict[str, Any]:
    function = schema.get("function") or schema
    return {
        "name": function.get("name", ""),
        "description": function.get("description", ""),
        "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
    }


def parse_response(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    text_parts: list[str] = []
    calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == TEXT_BLOCK:
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == TOOL_USE:
            calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "input": block.get("input") or {},
                }
            )
    return "\n".join(part for part in text_parts if part).strip(), calls, _stop(data)


def _assistant_message(message: dict[str, Any]) -> dict[str, Any] | None:
    blocks: list[dict[str, Any]] = []
    text = str(message.get("content") or "")
    if text:
        blocks.append({"type": TEXT_BLOCK, "text": text})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        blocks.append(
            {
                "type": TOOL_USE,
                "id": call.get("id") or "",
                "name": function.get("name") or "",
                "input": _as_object(function.get("arguments")),
            }
        )
    return {"role": ASSISTANT, "content": blocks} if blocks else None


def _result_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": USER,
        "content": [
            {
                "type": TOOL_RESULT,
                "tool_use_id": message.get("tool_call_id") or "",
                "content": str(message.get("content") or ""),
            }
        ],
    }


def _merged(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"] == USER:
            merged[-1] = {"role": USER, "content": _join(merged[-1]["content"], turn["content"])}
            continue
        merged.append(turn)
    return merged


def _join(left: Any, right: Any) -> Any:
    if isinstance(left, str) and isinstance(right, str):
        return left + "\n\n" + right
    return _as_blocks(left) + _as_blocks(right)


def _as_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return content
    return [{"type": TEXT_BLOCK, "text": str(content)}]


def _as_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stop(data: dict[str, Any]) -> str:
    return str(data.get("stop_reason") or "").strip()
