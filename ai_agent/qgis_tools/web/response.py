import codecs
import re
from typing import Any

HEADER_BYTES = 256
SNIFFED_BYTES = 2048
DEFAULT_CHARSET = "utf-8"
HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.IGNORECASE)
META_CHARSET = re.compile(rb"<meta[^>]*charset\s*=\s*[\"']?\s*([\w.:-]+)", re.IGNORECASE)
TEXT_TYPE_MARKS = ("json", "xml", "csv", "javascript", "yaml")


def redirect_of(reply: Any, limit: int) -> str:
    return header_of(reply, b"Location", limit)


def content_type_of(reply: Any) -> str:
    return header_of(reply, b"Content-Type", HEADER_BYTES).partition(";")[0].strip().lower()


def charset_of(reply: Any) -> str:
    found = HEADER_CHARSET.search(header_of(reply, b"Content-Type", HEADER_BYTES))
    return found.group(1).lower() if found else ""


def is_text_type(content_type: str) -> bool:
    kind = (content_type or "").lower()
    return not kind or kind.startswith("text/") or any(mark in kind for mark in TEXT_TYPE_MARKS)


def decoded_text(body: bytes, charset: str = "") -> str:
    declared = META_CHARSET.search(body[:SNIFFED_BYTES])
    for name in (charset, declared.group(1).decode("ascii", "ignore") if declared else "", DEFAULT_CHARSET):
        try:
            codecs.lookup(name)
        except LookupError:
            continue
        return body.decode(name, errors="replace")
    return body.decode(DEFAULT_CHARSET, errors="replace")


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
