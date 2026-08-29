import json
from typing import Any

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.core.llm.client import ApiResponseError, build_network_request
from ai_agent.core.llm.stream import SseAccumulator

STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
MILLISECONDS = 1000
STREAM_TIMED_OUT = "The streaming connection to {endpoint} went quiet and was closed."
STREAM_FAILED = "Could not stream from {endpoint}: {reason}."
ERROR_BODY_LIMIT = 300
ACCEPT_HEADER = {"Accept": "text/event-stream"}


def post_stream(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    completion: Any,
    timeout: int,
    verify_override: bool | None = None,
) -> dict[str, Any]:
    request = build_network_request(endpoint, {**headers, **ACCEPT_HEADER}, verify_override)
    payload = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    reply = QgsNetworkAccessManager.instance().post(request, payload)

    accumulator = SseAccumulator()
    error_tail: list[bytes] = []
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.setInterval(timeout * MILLISECONDS)
    watchdog.timeout.connect(loop.quit)

    def drain() -> None:
        raw = bytes(reply.readAll())
        if not raw:
            return
        if _status_of(reply) >= 400:
            error_tail.append(raw)
            return
        for event in accumulator.feed(raw):
            completion.take(event)

    reply.readyRead.connect(watchdog.start)
    reply.readyRead.connect(drain)
    reply.finished.connect(loop.quit)
    watchdog.start()
    if not reply.isFinished():
        loop.exec()
    watchdog.stop()

    timed_out = not reply.isFinished()
    if timed_out:
        reply.abort()
    drain()
    status = _status_of(reply)
    failure = _failure_of(reply)
    reply.deleteLater()

    if timed_out:
        raise ConnectionError(STREAM_TIMED_OUT.format(endpoint=endpoint))
    if status >= 400:
        text = b"".join(error_tail).decode("utf-8", errors="replace")
        raise ApiResponseError(status, text[:ERROR_BODY_LIMIT] or f"HTTP {status}")
    if failure:
        raise ConnectionError(STREAM_FAILED.format(endpoint=endpoint, reason=failure))
    return completion.response()


def _status_of(reply: Any) -> int:
    try:
        return int(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0


def _failure_of(reply: Any) -> str:
    try:
        if int(reply.error()) == 0:
            return ""
        return str(reply.errorString())
    except Exception:
        return ""
