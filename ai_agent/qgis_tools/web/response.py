from typing import Any


def redirect_of(reply: Any, limit: int) -> str:
    return header_of(reply, b"Location", limit)


def content_type_of(reply: Any) -> str:
    return header_of(reply, b"Content-Type", 256).partition(";")[0].strip().lower()


def header_of(reply: Any, name: bytes, limit: int) -> str:
    try:
        raw = bytes(reply.rawHeader(name))
    except Exception:
        return ""
    if not raw or len(raw) > limit:
        return ""
    return raw.decode("latin-1", errors="replace").strip()


def failure_of(reply: Any) -> str:
    try:
        code = integer(reply.error())
        if code == 0:
            return ""
        return f"network error {code}"
    except Exception:
        return "service unavailable"


def integer(value: Any) -> int:
    return int(getattr(value, "value", value))
