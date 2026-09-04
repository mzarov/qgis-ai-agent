import time
from collections.abc import Callable
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.llm.client import ApiResponseError

LOG_TAG = "AI Agent"
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.5, 4.0)
POLL_SECONDS = 0.25
FAST_FAILURE_SECONDS = 5.0
RETRY_LOG = "Model request failed ({reason}); retrying in {delay:.1f} s, attempt {attempt} of {total}."
SLEEP = time.sleep
CLOCK = time.monotonic


class ChunkGuard:
    def __init__(self, target: Callable[[str], None] | None):
        self._target = target
        self.delivered = 0

    def __call__(self, text: str) -> None:
        self.delivered += 1
        if self._target is not None:
            self._target(text)


def with_retries(
    attempt: Callable[[], Any],
    feedback: Any = None,
    delivered: Callable[[], int] = lambda: 0,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> Any:
    pause = sleep or SLEEP
    now = clock or CLOCK
    attempts = 0
    while True:
        attempts += 1
        started = now()
        try:
            return attempt()
        except (ApiResponseError, ConnectionError) as error:
            exhausted = attempts >= MAX_ATTEMPTS
            if exhausted or delivered() or is_cancelled(feedback) or not is_retryable(error, now() - started):
                raise
            delay = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
            QgsMessageLog.logMessage(
                RETRY_LOG.format(reason=_reason(error), delay=delay, attempt=attempts + 1, total=MAX_ATTEMPTS),
                LOG_TAG,
                Qgis.MessageLevel.Warning,
            )
            _pause(delay, feedback, pause)


def is_retryable(error: Exception, elapsed: float) -> bool:
    if isinstance(error, ApiResponseError):
        return error.status_code in RETRYABLE_STATUSES
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
