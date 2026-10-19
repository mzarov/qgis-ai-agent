import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.qgis_tools.common import network
from ai_agent.qgis_tools.common.network import Answer


class _Signal:
    def __init__(self, journal=None, name=""):
        self.slots = []
        self.kinds = []
        self._journal = journal
        self._name = name

    def connect(self, slot, kind=None):
        self.slots.append(slot)
        self.kinds.append(kind)
        if self._journal is not None:
            self._journal.append(f"connect {self._name}")

    def disconnect(self, slot=None):
        if self._journal is not None:
            self._journal.append(f"disconnect {self._name}")
        if slot is None:
            if not self.slots:
                raise TypeError("disconnect() failed between 'destroyed' and all its connections")
            self.slots = []
        elif slot in self.slots:
            self.slots.remove(slot)
        else:
            raise TypeError("slot was not connected")

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class _Reply:
    def __init__(self, chunks=(), status=200, error=0, headers=None, finished=False):
        self.readyRead = _Signal()
        self.finished = _Signal()
        self.destroyed = _Signal()
        self.destroyed.connect("PyQt's deletion monitor")
        self._chunks = list(chunks)
        self._status = status
        self._error = error
        self._headers = headers or {}
        self._finished = finished
        self.aborted = 0
        self.deleted = False

    def readAll(self):
        if self.deleted:
            raise RuntimeError("wrapped C/C++ object of type QNetworkReply has been deleted")
        return self._chunks.pop(0) if self._chunks else b""

    def isFinished(self):
        return self._finished

    def abort(self):
        self.aborted += 1
        self._finished = True
        self.finished.emit()

    def attribute(self, _name):
        return self._status

    def error(self):
        return self._error

    def errorString(self):
        return "Connection refused" if self._error else ""

    def rawHeaderList(self):
        return list(self._headers)

    def rawHeader(self, name):
        return self._headers[name]

    def deleteLater(self):
        self.deleted = True


class _Manager:
    def __init__(self, reply):
        self.reply = reply
        self.destroyed = _Signal()
        self.destroyed.connect("PyQt's deletion monitor")
        self.sent = []

    def get(self, request):
        self.sent.append((request, None))
        return self.reply

    def post(self, request, payload):
        self.sent.append((request, bytes(payload)))
        return self.reply


class _Loop:
    def __init__(self, during=None):
        self.ran = 0
        self._during = during

    def exec(self):
        self.ran += 1
        if self._during is not None:
            self._during()

    def quit(self):
        return None


class _Feedback:
    def __init__(self, cancelled=False, journal=None):
        self.canceled = _Signal()
        self.destroyed = _Signal(journal, "feedback")
        self._cancelled = cancelled

    def isCanceled(self):
        return self._cancelled


def _collect(into):
    return lambda chunk, status: into.append((chunk, status))


def _ignore(chunk, status):
    return None


class StreamedExchangeTest(unittest.TestCase):
    def exchange(self, reply, feedback=None, during=None, on_data=_ignore, idle_timeout_s=0, payload=b"{}"):
        manager = _Manager(reply)
        loops = []
        self.timers = []
        timer = network.QTimer

        def loop_factory():
            loops.append(_Loop(during))
            return loops[-1]

        def timer_factory():
            self.timers.append(timer())
            return self.timers[-1]

        with (
            mock.patch.object(network, "QgsNetworkAccessManager", SimpleNamespace(instance=lambda: manager)),
            mock.patch.object(network, "QEventLoop", loop_factory),
            mock.patch.object(network, "QTimer", timer_factory),
            mock.patch.object(network, "QByteArray", bytes),
        ):
            answer = network._streamed(object(), payload, feedback, on_data, idle_timeout_s)
        return answer, manager, loops[0]

    def test_chunks_reach_the_handler_with_the_status_and_the_answer_keeps_the_headers(self):
        seen = []
        reply = _Reply([b"data: 1\n\n", b"data: 2\n\n"], headers={b"Retry-After": b"7"})
        answer, manager, _ = self.exchange(
            reply, during=lambda: [reply.readyRead.emit(), reply.readyRead.emit()], on_data=_collect(seen)
        )
        self.assertEqual(seen, [(b"data: 1\n\n", 200), (b"data: 2\n\n", 200)])
        self.assertEqual(answer, Answer(status=200, headers={"retry-after": "7"}))
        self.assertEqual(manager.sent[0][1], b"{}")

    def test_deletion_reports_are_cut_before_the_worker_lets_go_of_its_objects(self):
        reply = _Reply(finished=True)
        _, manager, _ = self.exchange(reply)
        self.assertEqual((manager.destroyed.slots, reply.destroyed.slots), ([], []))
        self.assertTrue(reply.deleted)

    def test_an_instantly_finished_reply_does_not_enter_the_loop(self):
        _, _, loop = self.exchange(_Reply(finished=True))
        self.assertEqual(loop.ran, 0)

    def test_every_chunk_restarts_the_idle_timer(self):
        reply = _Reply([b"a", b"b"])
        self.exchange(reply, during=lambda: [reply.readyRead.emit(), reply.readyRead.emit()], idle_timeout_s=5)
        self.assertEqual(self.timers[0].started, 3, "started once, then again for each chunk")
        self.assertFalse(self.timers[0].isActive())

    def test_a_handler_failure_stops_the_exchange_and_comes_back_to_the_caller(self):
        reply = _Reply([b"bad"])

        def broken(chunk, status):
            raise ValueError("not an event")

        with self.assertRaisesRegex(ValueError, "not an event"):
            self.exchange(reply, during=reply.readyRead.emit, on_data=broken)
        self.assertEqual(reply.aborted, 1)
        self.assertTrue(reply.deleted)

    def test_cancelling_aborts_once_and_is_queued_to_the_working_thread(self):
        reply = _Reply()
        feedback = _Feedback()

        def during():
            slot = feedback.canceled.slots[0]
            slot()
            slot()

        answer, _, _ = self.exchange(reply, feedback, during=during)
        self.assertTrue(answer.cancelled)
        self.assertEqual(reply.aborted, 1)
        self.assertEqual(feedback.canceled.kinds, [network.Qt.ConnectionType.QueuedConnection])
        self.assertEqual(feedback.canceled.slots, [], "the feedback still reaches a finished exchange")

    def test_an_already_cancelled_feedback_never_waits(self):
        answer, _, loop = self.exchange(_Reply(), _Feedback(cancelled=True))
        self.assertTrue(answer.cancelled)
        self.assertEqual(loop.ran, 0)

    def test_a_silent_stream_times_out(self):
        reply = _Reply()
        answer, _, _ = self.exchange(reply, during=lambda: self.timers[0].fire(), idle_timeout_s=5)
        self.assertTrue(answer.timed_out)
        self.assertEqual(reply.aborted, 1)

    def test_a_late_ready_read_after_the_reply_is_gone_is_ignored(self):
        reply = _Reply(finished=True)
        self.exchange(reply)
        self.assertEqual((reply.readyRead.slots, reply.finished.slots), ([], []))

    def test_a_transport_failure_is_reported_with_its_reason(self):
        answer, _, _ = self.exchange(_Reply(status=None, error=1, finished=True))
        self.assertEqual((answer.status, answer.failed, answer.error), (0, True, "Connection refused"))

    def test_a_get_has_no_payload(self):
        _, manager, _ = self.exchange(_Reply(finished=True), payload=None)
        self.assertEqual(manager.sent[0][1], None)


class _Blocking:
    class ErrorCode:
        NoError = 0
        TimeoutError = 4

    code = 0
    made = []
    journal = []

    def __init__(self):
        self.downloadProgress = _Signal()
        self.destroyed = _Signal(_Blocking.journal, "request")
        self.calls = []
        _Blocking.made.append(self)

    def get(self, request, force, feedback):
        _Blocking.journal.append("get")
        self.calls.append(("get", None, feedback))
        return self.code

    def post(self, request, payload, force, feedback):
        _Blocking.journal.append("post")
        self.calls.append(("post", bytes(payload), feedback))
        return self.code

    def reply(self):
        content = _Reply(status=201, headers={b"X-Seen": b"yes"})
        content.content = lambda: b"answer"
        return content

    def errorMessage(self):
        return "Operation canceled" if self.code else ""


class BlockingSendTest(unittest.TestCase):
    def setUp(self):
        _Blocking.made = []
        _Blocking.journal = []
        _Blocking.code = 0
        for patch in (
            mock.patch.object(network, "QgsBlockingNetworkRequest", _Blocking),
            mock.patch.object(network, "QByteArray", bytes),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_plain_call_waits_on_a_blocking_request(self):
        progress = []
        answer = network.send(object(), b"{}", on_progress=lambda *counts: progress.append(counts))
        self.assertEqual((answer.status, answer.body), (201, b"answer"))
        self.assertEqual(answer.headers, {"x-seen": "yes"})
        self.assertFalse(answer.failed)
        (made,) = _Blocking.made
        self.assertEqual(made.calls, [("post", b"{}", None)])
        made.downloadProgress.emit(3, 10)
        self.assertEqual(progress, [(3, 10)])

    def test_every_python_made_sender_settles_its_disconnect_lookup_before_the_request_runs(self):
        feedback = _Feedback(journal=_Blocking.journal)
        application = SimpleNamespace(destroyed=_Signal(_Blocking.journal, "application"))
        with mock.patch.object(network, "QCoreApplication", SimpleNamespace(instance=lambda: application)):
            worker = threading.Thread(target=lambda: network.send(object(), None, feedback))
            worker.start()
            worker.join()
        settled = [
            f"{step} {name}" for name in ("request", "feedback", "application") for step in ("connect", "disconnect")
        ]
        self.assertEqual(_Blocking.journal, [*settled, "get"])

    def test_a_cancelled_blocking_request_says_so(self):
        _Blocking.code = 2
        answer = network.send(object(), None, _Feedback(cancelled=True))
        self.assertEqual((answer.failed, answer.cancelled, answer.error), (True, True, "Operation canceled"))

    def test_a_stream_never_makes_a_blocking_request(self):
        taken = []
        with mock.patch.object(network, "_streamed", lambda *args: taken.append(args) or Answer()):
            network.send(object(), b"{}", on_data=_ignore)
        self.assertEqual(len(taken), 1)
        self.assertEqual(_Blocking.made, [])


if __name__ == "__main__":
    unittest.main()
