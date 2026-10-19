import json
from typing import Any

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.qgis_tools.common.background import download_progress
from ai_agent.qgis_tools.common.network import send

USER_AGENT = b"AI Agent (QGIS plugin)"
JSON_TYPE = "application/json"
MAX_JSON_BYTES = 8 * 1024 * 1024


def get_json(url: str, feedback: Any = None) -> Any:
    return _decoded(_send(url, feedback=feedback), url)


def post_json(url: str, body: dict[str, Any]) -> Any:
    return _decoded(_send(url, json.dumps(body).encode("utf-8")), url)


def get_bytes(url: str, limit: int, feedback: Any = None) -> bytes:
    payload = _send(url, feedback=feedback)
    if len(payload) > limit:
        raise ValueError(
            f"{_host(url)} sent {len(payload) // 1024 // 1024} MB, over the limit of {limit // 1024 // 1024} MB. "
            "Pick a coarser scale or a smaller area."
        )
    return payload


def _send(url: str, body: bytes | None = None, feedback: Any = None) -> bytes:
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"User-Agent", USER_AGENT)
    if body is not None:
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, JSON_TYPE)
    progress = download_progress(feedback) if feedback is not None else None
    answer = send(request, body, feedback, progress)
    if answer.failed:
        reason = answer.error or "no answer"
        raise ValueError(f"{_host(url)} did not answer: {reason}. The service may be busy — retry later.")
    return answer.body


def _decoded(payload: bytes, url: str) -> Any:
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError(f"{_host(url)} sent an answer too large to read. Narrow the search down.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError(f"{_host(url)} sent something that is not JSON: {payload[:160]!r}.") from None


def _host(url: str) -> str:
    return QUrl(url).host() or url
