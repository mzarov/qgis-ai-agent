import json
import re

PRIORITY_KEYS = ("tool_calls", "text", "done")
FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def parse_model_json(reply: str) -> dict:
    raw = (reply or "").strip()
    if "```" in raw:
        match = FENCE_PATTERN.search(raw)
        if match:
            raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _parse_best_object(raw)


def _parse_best_object(raw: str) -> dict:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict]] = []
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


def _priority_score(candidate: dict) -> int:
    return sum(1 for key in PRIORITY_KEYS if key in candidate)


def parse_tool_arguments(raw_arguments) -> dict:
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    text = raw_arguments.strip() if isinstance(raw_arguments, str) else ""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = _parse_best_object(text)
        except json.JSONDecodeError:
            return {}
    return dict(parsed) if isinstance(parsed, dict) else {}
