import json
from typing import Any

from ai_agent.core.llm.dialects import DEFAULT_MAX_TOKENS

TEXT_BLOCK = "text"
IMAGE_BLOCK = "image"
IMAGE_URL_BLOCK = "image_url"
DATA_URL_PREFIX = "data:"
DEFAULT_IMAGE_MEDIA = "image/png"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
USER = "user"
ASSISTANT = "assistant"
SYSTEM = "system"
TOOL = "tool"
THINKING_BLOCK = "thinking"
REDACTED_THINKING_BLOCK = "redacted_thinking"
THINKING_BLOCKS = (THINKING_BLOCK, REDACTED_THINKING_BLOCK)
THINKING_KEY = "thinking_blocks"
MIN_THINKING_BUDGET = 1024
ANSWER_HEADROOM = 4096
SONNET_5_PREFIX = "claude-sonnet-5"


def build_body(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]] | None,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thinking_budget: int = 0,
) -> dict[str, Any]:
    budget = int(thinking_budget or 0)
    mode = _thinking_mode(model, budget)
    thinking_on = mode in ("enabled", "adaptive")
    system, turns = split_system(messages if thinking_on else _without_thinking(messages))
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max(max_tokens, budget + ANSWER_HEADROOM) if mode == "enabled" else max_tokens,
        "messages": turns,
    }
    if mode == "enabled":
        body["thinking"] = {"type": "enabled", "budget_tokens": budget}
    elif mode:
        body["thinking"] = {"type": mode}
    if system:
        body["system"] = system
    if tool_schemas:
        body["tools"] = [translate_tool(schema) for schema in tool_schemas]
    return body


def _thinking_mode(model: str, budget: int) -> str:
    if (model or "").strip().lower().startswith(SONNET_5_PREFIX):
        return "adaptive" if budget > 0 else "disabled"
    return "enabled" if budget >= MIN_THINKING_BUDGET else ""


def _without_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in message.items() if key != THINKING_KEY} for message in messages]


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
    content = message.get("content")
    if isinstance(content, list):
        blocks = [block for block in (_user_block(item) for item in content) if block]
        return {"role": USER, "content": blocks} if blocks else None
    text = str(content or "")
    return {"role": USER, "content": text} if text else None


def _user_block(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if item.get("type") == IMAGE_URL_BLOCK:
        media, data = _split_data_url(str((item.get(IMAGE_URL_BLOCK) or {}).get("url") or ""))
        if not data:
            return None
        return {"type": IMAGE_BLOCK, "source": {"type": "base64", "media_type": media, "data": data}}
    text = str(item.get("text") or "")
    return {"type": TEXT_BLOCK, "text": text} if text else None


def _split_data_url(url: str) -> tuple[str, str]:
    if not url.startswith(DATA_URL_PREFIX):
        return "", ""
    head, _, data = url.partition(",")
    media = head[len(DATA_URL_PREFIX) :].split(";")[0] or DEFAULT_IMAGE_MEDIA
    return media, data


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


def parse_thinking(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    blocks = [
        block for block in data.get("content") or [] if isinstance(block, dict) and block.get("type") in THINKING_BLOCKS
    ]
    text = "\n".join(str(block.get(THINKING_BLOCK) or "") for block in blocks if block.get(THINKING_BLOCK))
    return text.strip(), blocks


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
    if not blocks:
        return None
    thought = [block for block in message.get(THINKING_KEY) or [] if isinstance(block, dict)]
    return {"role": ASSISTANT, "content": thought + blocks}


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
