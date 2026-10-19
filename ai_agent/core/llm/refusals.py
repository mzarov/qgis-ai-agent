import json
import re
from typing import Any

from ai_agent.core.llm.client import ApiResponseError

UNSUPPORTED_STATUS_CODES = (400, 404, 422, 501)
REFUSAL_WORDS = (
    r"not supported|unsupported|not support|does not support|doesn't support|not available|"
    r"not allowed|not permitted|unrecognized|unrecognised|unknown|unexpected|extra inputs|"
    r"invalid (?:field|parameter|argument)"
)
NEVER_A_REFUSAL = re.compile(
    r"context[_ ]length|maximum context|context window|prompt is too long|too many tokens|"
    r"reduce the length|rate[_ ]limit|quota|invalid schema|bound to a different conversation|"
    r"prefix_binding|block_binding|invalid `?signature",
    re.IGNORECASE,
)
FEATURE_WORDS = {
    "tools": r"tools?|tool_choice|tool[_ ]calls?|function[_ ]calling|functions",
    "streaming": r"stream|streaming|stream_options|server-sent events|event-stream",
    "thinking": r"thinking|budget_tokens|reasoning(?:_effort|Effort)?",
}
FEATURE_PARAMETERS = {
    "tools": ("tools", "tool_choice", "functions"),
    "streaming": ("stream", "stream_options"),
    "thinking": ("thinking", "reasoning", "reasoning_effort", "reasoningeffort"),
}
VALUE_REFUSALS = {"thinking": r"must be one of|invalid value|not a valid"}
NEARBY = 60


def _pattern(feature: str) -> re.Pattern[str]:
    words = FEATURE_WORDS[feature]
    refusal = "|".join(filter(None, (REFUSAL_WORDS, VALUE_REFUSALS.get(feature))))
    return re.compile(
        rf"\b(?:{words})\b.{{0,{NEARBY}}}\b(?:{refusal})\b|\b(?:{refusal})\b.{{0,{NEARBY}}}\b(?:{words})\b",
        re.IGNORECASE | re.DOTALL,
    )


PATTERNS = {feature: _pattern(feature) for feature in FEATURE_WORDS}


def refuses(err: ApiResponseError, feature: str) -> bool:
    if err.status_code not in UNSUPPORTED_STATUS_CODES:
        return False
    body = err.body or ""
    if NEVER_A_REFUSAL.search(body):
        return False
    if _structured_parameter(body) in FEATURE_PARAMETERS[feature]:
        return True
    return bool(PATTERNS[feature].search(body))


def tools_unsupported(err: ApiResponseError) -> bool:
    return refuses(err, "tools")


def thinking_unsupported(err: ApiResponseError) -> bool:
    return refuses(err, "thinking")


def streaming_unsupported(err: ApiResponseError) -> bool:
    return refuses(err, "streaming")


def may_reject_images(err: ApiResponseError, statuses: tuple[int, ...]) -> bool:
    return err.status_code in statuses and not NEVER_A_REFUSAL.search(err.body or "")


def _structured_parameter(body: str) -> str:
    try:
        data: Any = json.loads(body)
    except (TypeError, ValueError):
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return ""
    parameter = str(error.get("param") or "").strip().lower()
    return parameter.split(".")[0].split("[")[0]
