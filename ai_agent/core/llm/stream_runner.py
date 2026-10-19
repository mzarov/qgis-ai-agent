import json
from typing import Any

from ai_agent.core.llm.client import ApiResponseError, ModelTimeout, build_network_request, retry_after_of
from ai_agent.core.llm.dialects import safe_endpoint_label
from ai_agent.core.llm.stream import SseAccumulator
from ai_agent.qgis_tools.common.network import send

STREAM_TIMED_OUT = "The streaming connection to {endpoint} went quiet and was closed."
STREAM_CANCELLED = "The streaming connection to {endpoint} was cancelled."
STREAM_FAILED = "Could not stream from {endpoint}: {reason}."
STREAM_INCOMPLETE = "The stream from {endpoint} ended before the answer was complete."
STREAM_EVENTS_KEY = "_stream_events"
ERROR_STATUS = {"overloaded_error": 529, "rate_limit_error": 429, "api_error": 500, "timeout_error": 504}
DEFAULT_ERROR_STATUS = 502
ERROR_BODY_LIMIT = 300
ACCEPT_HEADER = {"Accept": "text/event-stream"}


def post_stream(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    completion: Any,
    timeout: int,
    verify_override: bool | None = None,
    feedback: Any = None,
) -> dict[str, Any]:
    request = build_network_request(endpoint, {**headers, **ACCEPT_HEADER}, verify_override, timeout)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    accumulator = SseAccumulator()
    error_tail: list[bytes] = []

    def take(chunk: bytes, status: int) -> None:
        if status >= 400:
            error_tail.append(chunk)
            return
        for event in accumulator.feed(chunk):
            completion.take(event)

    answer = send(request, payload, feedback, on_data=take, idle_timeout_s=timeout)
    if answer.cancelled:
        raise ConnectionError(STREAM_CANCELLED.format(endpoint=safe_endpoint_label(endpoint)))
    if answer.timed_out:
        raise ModelTimeout(STREAM_TIMED_OUT.format(endpoint=safe_endpoint_label(endpoint)))
    if answer.status >= 400:
        text = b"".join(error_tail).decode("utf-8", errors="replace")
        raise ApiResponseError(
            answer.status, text[:ERROR_BODY_LIMIT] or f"HTTP {answer.status}", retry_after=retry_after_of(answer)
        )
    if answer.failed:
        raise ConnectionError(STREAM_FAILED.format(endpoint=safe_endpoint_label(endpoint), reason=answer.error))
    for event in accumulator.flush():
        completion.take(event)
    return _finished_response(completion, accumulator, endpoint)


def _finished_response(completion: Any, accumulator: SseAccumulator, endpoint: str) -> dict[str, Any]:
    error = getattr(completion, "error", None)
    if error:
        kind = str(error.get("type") or error.get("code") or "")
        raise ApiResponseError(ERROR_STATUS.get(kind, DEFAULT_ERROR_STATUS), json.dumps(error, ensure_ascii=False))
    if accumulator.event_count == 0:
        plain = accumulator.plain_json()
        response = plain if isinstance(plain, dict) else completion.response()
        return {**response, STREAM_EVENTS_KEY: 0}
    if not getattr(completion, "finished", True):
        raise ConnectionError(STREAM_INCOMPLETE.format(endpoint=safe_endpoint_label(endpoint)))
    return {**completion.response(), STREAM_EVENTS_KEY: accumulator.event_count}
