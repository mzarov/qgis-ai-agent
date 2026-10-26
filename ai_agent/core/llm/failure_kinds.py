import json
import re
from pathlib import PurePath
from types import TracebackType

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
ERROR_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
KIND = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
# Digits are refused so an account or request id can never pass for a code.
PROVIDER_CODE = re.compile(r"^[a-z][a-z_]{1,39}$")
CODE_FIELDS = ("code", "type", "status")
PACKAGE = "ai_agent"


class TurnFailure(str):
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
        return _http_kind(status, error.body) if isinstance(status, int) else OTHER
    if isinstance(error, ConnectionError):
        return CONNECTION
    return _error_kind(error)


def _provider_code(body: str) -> str:
    try:
        value = json.loads(body or "")
    except (ValueError, RecursionError):
        return ""
    if isinstance(value, list) and value:
        value = value[0]
    error = value.get("error", value) if isinstance(value, dict) else None
    if not isinstance(error, dict):
        return ""
    for field in CODE_FIELDS:
        code = error.get(field)
        if isinstance(code, str) and PROVIDER_CODE.match(code.lower()):
            return code.lower()
    return ""


def _http_kind(status: int, body: str) -> str:
    kind = f"http_{status}_{_provider_code(body)}".rstrip("_")
    return kind if KIND.match(kind) else f"http_{status}"


def _error_kind(error: BaseException) -> str:
    name = type(error).__name__.lower()
    if not ERROR_NAME.match(name):
        return OTHER
    place = _plugin_frame(error.__traceback__)
    located = f"{name}_{place}" if place else name
    return located if KIND.match(located) else name


def _plugin_frame(trace: TracebackType | None) -> str:
    place = ""
    while trace is not None:
        path = PurePath(trace.tb_frame.f_code.co_filename)
        if PACKAGE in path.parts:
            place = f"{path.stem.lower()}_{trace.tb_lineno}"
        trace = trace.tb_next
    return place


def turn_failure(error: BaseException) -> TurnFailure:
    return TurnFailure(str(error), failure_kind(error))
