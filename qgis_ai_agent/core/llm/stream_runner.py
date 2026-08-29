import json
from collections.abc import Callable
from typing import Any

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis_ai_agent.core.llm.client import ApiResponseError
from qgis_ai_agent.core.llm.stream import SseAccumulator, StreamedCompletion

STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
MILLISECONDS = 1000
STREAM_TIMED_OUT = "The streaming connection to {endpoint} went quiet and was closed."
ERROR_BODY_LIMIT = 300


def post_stream(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    on_text: Callable[[str], None],
    timeout: int,
) -> dict[str, Any]:
    request = QNetworkRequest(QUrl(endpoint))
    for name, value in headers.items():
        request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    payload = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    manager = QgsNetworkAccessManager.instance()
    reply = manager.post(request, payload)
    accumulator = SseAccumulator()
    completion = StreamedCompletion(on_text)
    error_tail: list[bytes] = []
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.setInterval(timeout * MILLISECONDS)
    watchdog.timeout.connect(loop.quit)

    def drain() -> None:
        watchdog.start()
        raw = bytes(reply.readAll())
        if _status_of(reply) >= 400:
            error_tail.append(raw)
            return
        for event in accumulator.feed(raw):
            completion.take(event)

    reply.readyRead.connect(drain)
    reply.finished.connect(loop.quit)
    watchdog.start()
    loop.exec()

    timed_out = not watchdog.isActive() and not reply.isFinished()
    if timed_out:
        reply.abort()
    drain()
    status = _status_of(reply)
    reply.deleteLater()
    if timed_out:
        raise ConnectionError(STREAM_TIMED_OUT.format(endpoint=endpoint))
    if status >= 400:
        text = b"".join(error_tail).decode("utf-8", errors="replace")
        raise ApiResponseError(status, text[:ERROR_BODY_LIMIT] or f"HTTP {status}")
    if reply.error() != reply.NetworkError.NoError:
        raise ConnectionError(f"Could not stream from {endpoint}: {reply.errorString()}.")
    return completion.response()


def _status_of(reply: Any) -> int:
    try:
        return int(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0
