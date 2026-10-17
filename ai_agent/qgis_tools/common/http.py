"""Plain HTTPS calls to fixed hosts, the open-data catalogue and the QGIS plugin repository.

They run on the QGIS network stack, so proxy and SSL settings apply.
"""

import json
from typing import Any

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.qgis_tools.common.background import download_progress

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
    """The answer's bytes; safe off the main thread, where `feedback` can cancel the request."""
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"User-Agent", USER_AGENT)
    caller = QgsBlockingNetworkRequest()
    if feedback is not None:
        caller.downloadProgress.connect(download_progress(feedback))
    if body is None:
        code = caller.get(request, False, feedback)
    else:
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, JSON_TYPE)
        code = caller.post(request, QByteArray(body), False, feedback)
    if code != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise ValueError(f"{_host(url)} did not answer: {_message(caller)}. The service may be busy — retry later.")
    return bytes(caller.reply().content())


def _decoded(payload: bytes, url: str) -> Any:
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError(f"{_host(url)} sent an answer too large to read. Narrow the search down.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError(f"{_host(url)} sent something that is not JSON: {payload[:160]!r}.") from None


def _message(caller: Any) -> str:
    try:
        return str(caller.errorMessage()) or "no answer"
    except Exception:
        return "no answer"


def _host(url: str) -> str:
    return QUrl(url).host() or url
