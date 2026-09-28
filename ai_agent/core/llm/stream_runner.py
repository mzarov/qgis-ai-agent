import json
from typing import Any

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QByteArray, QEventLoop, QObject, Qt, QTimer, pyqtSlot
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.core.llm.client import ApiResponseError, build_network_request, retry_after_of
from ai_agent.core.llm.dialects import safe_endpoint_label
from ai_agent.core.llm.stream import SseAccumulator

STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
MILLISECONDS = 1000
STREAM_TIMED_OUT = "The streaming connection to {endpoint} went quiet and was closed."
STREAM_CANCELLED = "The streaming connection to {endpoint} was cancelled."
STREAM_FAILED = "Could not stream from {endpoint}: {reason}."
STREAM_INCOMPLETE = "The stream from {endpoint} ended before the answer was complete."
STREAM_EVENTS_KEY = "_stream_events"
ERROR_STATUS = {"overloaded_error": 529, "rate_limit_error": 429, "api_error": 500, "timeout_error": 504}
DEFAULT_ERROR_STATUS = 502
ERROR_BODY_LIMIT = 300
ACCEPT_HEADER = {"Accept": "text/event-stream"}


def _queued_connection() -> Any:
    return Qt.ConnectionType.QueuedConnection


class _StreamCancellation(QObject):
    def __init__(self, reply: Any, loop: QEventLoop):
        super().__init__()
        self.reply = reply
        self.loop = loop
        self.cancelled = False

    @pyqtSlot()
    def cancel(self) -> None:
        if self.cancelled:
            return
        self.cancelled = True
        self.reply.abort()
        self.loop.quit()


def post_stream(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    completion: Any,
    timeout: int,
    verify_override: bool | None = None,
    feedback: Any = None,
) -> dict[str, Any]:
    request = build_network_request(endpoint, {**headers, **ACCEPT_HEADER}, verify_override, timeout)
    payload = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    reply = QgsNetworkAccessManager.instance().post(request, payload)

    accumulator = SseAccumulator()
    error_tail: list[bytes] = []
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.setInterval(timeout * MILLISECONDS)
    watchdog.timeout.connect(loop.quit)
    cancellation = _StreamCancellation(reply, loop)

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
    if feedback is not None:
        feedback.canceled.connect(cancellation.cancel, _queued_connection())
        if feedback.isCanceled():
            cancellation.cancel()
    watchdog.start()
    if not reply.isFinished():
        loop.exec()
    watchdog.stop()
    if feedback is not None:
        try:
            feedback.canceled.disconnect(cancellation.cancel)
        except (RuntimeError, TypeError):
            pass

    timed_out = not cancellation.cancelled and not reply.isFinished()
    if timed_out:
        reply.abort()
    drain()
    status = _status_of(reply)
    failure = _failure_of(reply)
    retry_after = retry_after_of(reply)
    reply.deleteLater()

    if cancellation.cancelled:
        raise ConnectionError(STREAM_CANCELLED.format(endpoint=safe_endpoint_label(endpoint)))
    if timed_out:
        raise ConnectionError(STREAM_TIMED_OUT.format(endpoint=safe_endpoint_label(endpoint)))
    if status >= 400:
        text = b"".join(error_tail).decode("utf-8", errors="replace")
        raise ApiResponseError(status, text[:ERROR_BODY_LIMIT] or f"HTTP {status}", retry_after=retry_after)
    if failure:
        raise ConnectionError(STREAM_FAILED.format(endpoint=safe_endpoint_label(endpoint), reason=failure))
    for event in accumulator.flush():
        completion.take(event)
    return _finished_response(completion, accumulator, endpoint)


def _finished_response(completion: Any, accumulator: SseAccumulator, endpoint: str) -> dict[str, Any]:
    """Turn a closed stream into a response, or raise what really happened.

    An error event inside a 200 stream (an overloaded model, an upstream
    failure) is raised as an API error so the retry layer sees it; a stream
    that closed without its terminator is an incomplete answer, not a short
    one. A server that ignored `stream` and sent one plain JSON body is read as
    that body.
    """
    error = getattr(completion, "error", None)
    if error:
        kind = str(error.get("type") or error.get("code") or "")
        raise ApiResponseError(ERROR_STATUS.get(kind, DEFAULT_ERROR_STATUS), json.dumps(error, ensure_ascii=False))
    if accumulator.event_count == 0:
        plain = accumulator.plain_json()
        response = plain if isinstance(plain, dict) else completion.response()
        return {**response, STREAM_EVENTS_KEY: 0}
    if not getattr(completion, "finished", True):
        raise ConnectionError(STREAM_INCOMPLETE.format(endpoint=safe_endpoint_label(endpoint)))
    return {**completion.response(), STREAM_EVENTS_KEY: accumulator.event_count}


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
