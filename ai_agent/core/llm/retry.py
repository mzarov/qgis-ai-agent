import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.llm.client import ApiResponseError, ModelTimeout

LOG_TAG = "AI Agent"
RETRYABLE_STATUSES = frozenset({408, 425, 429})
OVERLOAD_STATUSES = frozenset({429, 503, 529})
SERVER_ERROR = 500
MAX_RETRY_AFTER_SECONDS = 30.0
QUOTA_MARKERS = ("insufficient_quota", "billing", "credit balance")
MAX_ATTEMPTS = 3
MAX_OVERLOAD_ATTEMPTS = 5
BACKOFF_SECONDS = (1.5, 4.0, 10.0, 20.0)
POLL_SECONDS = 0.25
FAST_FAILURE_SECONDS = 5.0
RETRY_LOG = "Model request failed ({reason}); retrying in {delay:.1f} s, attempt {attempt} of {total}."
SLEEP = time.sleep
CLOCK = time.monotonic


@dataclass(frozen=True)
class RetryNotice:
    seconds: float
    attempt: int
    total: int
    busy: bool


class ChunkGuard:
    def __init__(self, target: Callable[[str], None] | None):
        self._target = target
        self.delivered = 0

    def __call__(self, text: str) -> None:
        self.delivered += 1
        if self._target is not None:
            self._target(text)

    def wrap(self, target: Callable[[str], None] | None) -> Callable[[str], None] | None:
        if target is None:
            return None

        def counted(text: str) -> None:
            self.delivered += 1
            target(text)

        return counted


def with_retries[T](
    attempt: Callable[[], T],
    feedback: Any = None,
    delivered: Callable[[], int] = lambda: 0,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    on_retry: Callable[[RetryNotice], None] | None = None,
) -> T:
    # Runs on the request's own thread: on_retry must only hand the notice on, e.g. emit a signal.
    pause = sleep or SLEEP
    now = clock or CLOCK
    attempts = 0
    while True:
        attempts += 1
        started = now()
        try:
            return attempt()
        except (ApiResponseError, ConnectionError) as error:
            total = attempts_for(error)
            exhausted = attempts >= total
            if exhausted or delivered() or is_cancelled(feedback) or not is_retryable(error, now() - started):
                raise
            delay = retry_delay(error, attempts)
            QgsMessageLog.logMessage(
                RETRY_LOG.format(reason=_reason(error), delay=delay, attempt=attempts + 1, total=total),
                LOG_TAG,
                Qgis.MessageLevel.Warning,
            )
            if on_retry is not None:
                on_retry(RetryNotice(delay, attempts + 1, total, is_overload(error)))
            _pause(delay, feedback, pause)


def retry_delay(error: Exception, attempts: int) -> float:
    hinted = getattr(error, "retry_after", None)
    if isinstance(hinted, (int, float)) and hinted > 0:
        return min(float(hinted), MAX_RETRY_AFTER_SECONDS)
    return BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]


def is_overload(error: Exception) -> bool:
    return isinstance(error, ApiResponseError) and error.status_code in OVERLOAD_STATUSES


def attempts_for(error: Exception) -> int:
    return MAX_OVERLOAD_ATTEMPTS if is_overload(error) else MAX_ATTEMPTS


def is_retryable(error: Exception, elapsed: float) -> bool:
    if isinstance(error, ApiResponseError):
        if error.status_code == 429 and any(marker in (error.body or "").lower() for marker in QUOTA_MARKERS):
            return False
        return error.status_code in RETRYABLE_STATUSES or error.status_code >= SERVER_ERROR
    if isinstance(error, ModelTimeout):
        return False
    return isinstance(error, ConnectionError) and elapsed < FAST_FAILURE_SECONDS


def is_cancelled(feedback: Any) -> bool:
    try:
        return bool(feedback is not None and feedback.isCanceled())
    except Exception:
        return False


def _pause(delay: float, feedback: Any, sleep: Callable[[float], None]) -> None:
    remaining = delay
    while remaining > 0 and not is_cancelled(feedback):
        step = min(POLL_SECONDS, remaining)
        sleep(step)
        remaining -= step


def _reason(error: Exception) -> str:
    if isinstance(error, ApiResponseError):
        return f"HTTP {error.status_code}"
    return "connection failed"
