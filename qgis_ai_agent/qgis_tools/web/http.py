from typing import Any
from urllib.parse import quote

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

USER_AGENT = "qgis-ai-agent (QGIS plugin; https://github.com/mzarov/qgis-ai-agent)"
MAX_BODY_BYTES = 2_000_000
ALLOWED_SCHEMES = ("http", "https")
FETCH_FAILED = "Could not fetch {url}: {reason}."


def checked_url(raw: Any) -> str:
    url = str(raw or "").strip()
    if not url:
        raise ValueError("The URL is empty.")
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Only http and https URLs are fetched, got '{url}'.")
    return url


def get_text(url: str, extra_headers: dict[str, str] | None = None) -> str:
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
    request.setRawHeader(b"Accept-Language", "ru,en;q=0.8")
    for name, value in (extra_headers or {}).items():
        request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    caller = QgsBlockingNetworkRequest()
    if caller.get(request) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise ValueError(FETCH_FAILED.format(url=url, reason=_reason(caller)))
    body = bytes(caller.reply().content())[:MAX_BODY_BYTES]
    return body.decode("utf-8", errors="replace")


def encoded(value: str) -> str:
    return quote(str(value or ""), safe="")


def _reason(caller: Any) -> str:
    try:
        return caller.errorMessage() or "service unavailable"
    except Exception:
        return "service unavailable"
