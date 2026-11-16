import json
import re
from typing import Any

PRIORITY_KEYS = ("tool_calls", "text", "done")
FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def parse_model_json(reply: str) -> dict[str, Any]:
    raw = (reply or "").strip()
    parsed = _loaded_object(raw)
    # Only an unparsable reply is unwrapped: a fence inside a JSON string is part of the answer.
    if parsed is None and "```" in raw:
        match = FENCE_PATTERN.search(raw)
        if match:
            raw = match.group(1).strip()
            parsed = _loaded_object(raw)
    return parsed if parsed is not None else _parse_best_object(raw)


def _loaded_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_best_object(raw: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index, char in enumerate(raw):
        if char not in "{[":
            continue
        try:
            parsed, end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates.append((index + end, parsed))

    if not candidates:
        raise json.JSONDecodeError("No valid JSON object found", raw, 0)

    return max(candidates, key=lambda item: (_priority_score(item[1]), item[0]))[1]


def _priority_score(candidate: dict[str, Any]) -> int:
    return sum(1 for key in PRIORITY_KEYS if key in candidate)


def parse_tool_arguments(raw_arguments: object) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    text = raw_arguments.strip() if isinstance(raw_arguments, str) else ""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Only the outermost object: a nested one would run the tool with the wrong arguments.
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text[max(text.find("{"), 0) :])
        except json.JSONDecodeError:
            return {}
    return dict(parsed) if isinstance(parsed, dict) else {}
