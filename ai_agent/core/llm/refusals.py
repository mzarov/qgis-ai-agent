from ai_agent.core.llm.client import ApiResponseError

UNSUPPORTED_STATUS_CODES = (400, 404, 422, 501)
UNSUPPORTED_MARKERS = (
    "tools",
    "tool_choice",
    "function",
    "unsupported",
    "unrecognized",
    "unknown field",
    "not supported",
)
THINKING_MARKERS = ("thinking", "budget_tokens", "reasoning")
STREAMING_MARKERS = UNSUPPORTED_MARKERS + ("stream", "sse", "event-stream")


def _refused(err: ApiResponseError, markers: tuple[str, ...]) -> bool:
    if err.status_code not in UNSUPPORTED_STATUS_CODES:
        return False
    body = (err.body or "").lower()
    return any(marker in body for marker in markers)


def tools_unsupported(err: ApiResponseError) -> bool:
    return _refused(err, UNSUPPORTED_MARKERS)


def thinking_unsupported(err: ApiResponseError) -> bool:
    return _refused(err, THINKING_MARKERS)


def streaming_unsupported(err: ApiResponseError) -> bool:
    return _refused(err, STREAMING_MARKERS)
