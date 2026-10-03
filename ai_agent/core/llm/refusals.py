"""Telling "this endpoint does not support feature X" apart from any other 4xx.

A refusal is remembered per endpoint and model and switches the feature off for
good, so a false positive is expensive: one context-length overflow or one bad
tool schema used to disable streaming, tools and images at once. A body counts
as a refusal only when it names the feature next to a refusal phrase, or when a
structured error points at the feature's parameter.
"""

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
    "images": r"images?|image_url|vision|multimodal",
}
FEATURE_PARAMETERS = {
    "tools": ("tools", "tool_choice", "functions"),
    "streaming": ("stream", "stream_options"),
    "thinking": ("thinking", "reasoning", "reasoning_effort", "reasoningeffort"),
    "images": ("image_url",),
}
# Rejecting a value counts only for thinking: the plugin sends one fixed reasoning
# value, so a server that accepts others ("must be one of none, default") is best
# served by leaving the parameter out. For tools the same words mean a bad schema.
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


def images_unsupported(err: ApiResponseError) -> bool:
    return refuses(err, "images")


def may_reject_images(err: ApiResponseError, statuses: tuple[int, ...]) -> bool:
    """Worth one retry without images: an image-shaped status that is not a size or quota error.

    The capability is remembered only when that retry succeeds.
    """
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
