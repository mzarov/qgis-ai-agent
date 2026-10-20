from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QByteArray, QCoreApplication, QEventLoop, QObject, Qt, QTimer, pyqtSlot
from qgis.PyQt.QtNetwork import QNetworkRequest

STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
MILLISECONDS = 1000
QGIS_TIMEOUT_TIMER = "timeoutTimer"
QGIS_TIMER_MARGIN_MS = 1000

DataHandler = Callable[[bytes, int], None]
ProgressHandler = Callable[[int, int], None]


@dataclass(frozen=True)
class Answer:
    status: int = 0
    body: bytes = b""
    failed: bool = False
    error: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    cancelled: bool = False
    timed_out: bool = False


def send(
    request: QNetworkRequest,
    payload: bytes | None = None,
    feedback: Any = None,
    on_progress: ProgressHandler | None = None,
    on_data: DataHandler | None = None,
    idle_timeout_s: float = 0,
) -> Answer:
    if on_data is None:
        return _blocking(request, payload, feedback, on_progress)
    return _streamed(request, payload, feedback, on_data, idle_timeout_s)


def network_timeout_s() -> float:
    try:
        return max(0, int(QgsNetworkAccessManager.timeout())) / MILLISECONDS
    except (TypeError, ValueError, RuntimeError):
        return 0.0


def _blocking(
    request: QNetworkRequest, payload: bytes | None, feedback: Any, on_progress: ProgressHandler | None
) -> Answer:
    caller = QgsBlockingNetworkRequest()
    # Python-made senders wired to objects the request deletes without the GIL: itself, its feedback, the app.
    for sender in (caller, feedback, QCoreApplication.instance()):
        if sender is not None:
            _settle_disconnect_lookup(sender)
    if on_progress is not None:
        caller.downloadProgress.connect(on_progress)
    if payload is None:
        code = caller.get(request, False, feedback)
    else:
        code = caller.post(request, QByteArray(payload), False, feedback)
    content = caller.reply()
    failed = code != QgsBlockingNetworkRequest.ErrorCode.NoError
    return Answer(
        status=_status(content),
        body=bytes(content.content()),
        failed=failed,
        error=str(caller.errorMessage() or "") if failed else "",
        headers=_headers(content),
        cancelled=failed and feedback is not None and bool(feedback.isCanceled()),
        timed_out=code == QgsBlockingNetworkRequest.ErrorCode.TimeoutError,
    )


def _settle_disconnect_lookup(item: Any) -> None:
    # Qt calls disconnectNotify under a lock; sip takes the GIL there until a lookup has cached "not overridden".
    item.destroyed.connect(_ignore)
    item.destroyed.disconnect(_ignore)


def _ignore(*_args: Any) -> None:
    return None


def _streamed(
    request: QNetworkRequest, payload: bytes | None, feedback: Any, on_data: DataHandler, idle_timeout_s: float
) -> Answer:
    manager = _untracked(QgsNetworkAccessManager.instance())
    reply = manager.get(request) if payload is None else manager.post(request, QByteArray(payload))
    if idle_timeout_s > 0:
        _outlast_qgis_timeout(reply, idle_timeout_s)
    exchange = _Exchange(_untracked(reply), on_data, idle_timeout_s)
    if feedback is not None:
        feedback.canceled.connect(exchange.cancel, Qt.ConnectionType.QueuedConnection)
        if feedback.isCanceled():
            exchange.cancel()
    try:
        exchange.wait()
    finally:
        if feedback is not None:
            _disconnect(feedback.canceled, exchange.cancel)
    return exchange.finish()


def _outlast_qgis_timeout(reply: Any, idle_timeout_s: float) -> None:
    # QGIS aborts a reply quiet for its global network timeout, whatever the request asked: the idle limit governs.
    timer = reply.findChild(QTimer, QGIS_TIMEOUT_TIMER)
    if timer is None:
        return
    _untracked(timer)
    wanted = int(idle_timeout_s * MILLISECONDS) + QGIS_TIMER_MARGIN_MS
    if timer.interval() < wanted:
        timer.setInterval(wanted)


def _untracked(item: Any) -> Any:
    # PyQt reports a worker-made QObject's deletion to the main thread by address, late enough to kill a newer wrapper.
    _disconnect(item.destroyed)
    return item


class _Exchange(QObject):
    def __init__(self, reply: Any, on_data: DataHandler, idle_timeout_s: float) -> None:
        super().__init__()
        self.reply = reply
        self.loop = QEventLoop()
        self.cancelled = False
        self.timed_out = False
        self._on_data = on_data
        self._failure: BaseException | None = None
        self._idle = QTimer()
        self._idle.setSingleShot(True)
        self._idle.setInterval(int(idle_timeout_s * MILLISECONDS))
        self._watching = idle_timeout_s > 0
        self._idle.timeout.connect(self.time_out)
        reply.readyRead.connect(self.read)
        reply.finished.connect(self.loop.quit)

    def wait(self) -> None:
        if self._watching:
            self._idle.start()
        if not self.reply.isFinished():
            self.loop.exec()
        self._idle.stop()

    @pyqtSlot()
    def read(self) -> None:
        if self._watching:
            self._idle.start()
        self._drain()

    def _drain(self) -> None:
        if self._failure is not None:
            return
        # Never out of a slot: an exception escaping one aborts QGIS.
        try:
            chunk = bytes(self.reply.readAll())
            if chunk:
                self._on_data(chunk, _status(self.reply))
        except Exception as failure:
            self._fail(failure)

    @pyqtSlot()
    def cancel(self) -> None:
        if not self.cancelled:
            self.cancelled = True
            self._stop()

    @pyqtSlot()
    def time_out(self) -> None:
        try:
            finished = self.reply.isFinished()
        except RuntimeError:
            finished = False
        if not finished:
            self.timed_out = True
            self._stop()

    def _fail(self, failure: BaseException) -> None:
        self._failure = failure
        self._stop()

    def _stop(self) -> None:
        try:
            self.reply.abort()
        except RuntimeError:
            pass
        self.loop.quit()

    def finish(self) -> Answer:
        self._drain()
        reply = self.reply
        _disconnect(reply.readyRead, self.read)
        _disconnect(reply.finished, self.loop.quit)
        failed = _integer(reply.error()) != 0
        answer = Answer(
            status=_status(reply),
            failed=failed,
            error=str(reply.errorString() or "") if failed else "",
            headers=_headers(reply),
            cancelled=self.cancelled,
            timed_out=self.timed_out,
        )
        reply.deleteLater()
        if self._failure is not None:
            raise self._failure
        return answer


def _status(reply: Any) -> int:
    try:
        return _integer(reply.attribute(STATUS_ATTRIBUTE) or 0)
    except (TypeError, ValueError):
        return 0


def _integer(value: Any) -> int:
    return int(getattr(value, "value", value))


def _headers(reply: Any) -> dict[str, str]:
    headers = {}
    for name in reply.rawHeaderList():
        headers[bytes(name).decode("latin-1").lower()] = bytes(reply.rawHeader(name)).decode("latin-1")
    return headers


def _disconnect(signal: Any, slot: Any = None) -> None:
    try:
        if slot is None:
            signal.disconnect()
        else:
            signal.disconnect(slot)
    except (RuntimeError, TypeError):
        pass
