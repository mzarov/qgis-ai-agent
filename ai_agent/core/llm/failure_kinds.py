"""What kind of failure ended a model request, so the chat can say it plainly; the message stays as it was.

The worker thread knows the exception; the main thread only gets a message.
`TurnFailure` is that message with the kind attached, a `str` still, so every
handler that took a string keeps taking it.
"""

from ai_agent.core.llm.client import ApiResponseError, ModelTimeout, SetupError
from ai_agent.core.llm.retry import QUOTA_MARKERS, is_overload

CONNECTION = "connection"
TIMEOUT = "timeout"
AUTH = "auth"
QUOTA = "quota"
BUSY = "busy"
NOT_FOUND = "not_found"
SETUP = "setup"
OTHER = "other"
AUTH_STATUSES = frozenset({401, 403})
NOT_FOUND_STATUS = 404
RATE_LIMITED = 429


class TurnFailure(str):
    """A failed request's message, carrying its kind across the thread boundary."""

    kind: str

    def __new__(cls, message: str, kind: str) -> "TurnFailure":
        failure = super().__new__(cls, message)
        failure.kind = kind
        return failure


def failure_kind(error: BaseException) -> str:
    if isinstance(error, ModelTimeout):
        return TIMEOUT
    if isinstance(error, SetupError):
        return SETUP
    if isinstance(error, ApiResponseError):
        status = error.status_code
        if status in AUTH_STATUSES:
            return AUTH
        if status == RATE_LIMITED and any(marker in (error.body or "").lower() for marker in QUOTA_MARKERS):
            return QUOTA
        if is_overload(error):
            return BUSY
        if status == NOT_FOUND_STATUS:
            return NOT_FOUND
        return OTHER
    if isinstance(error, ConnectionError):
        return CONNECTION
    return OTHER


def turn_failure(error: BaseException) -> TurnFailure:
    return TurnFailure(str(error), failure_kind(error))
