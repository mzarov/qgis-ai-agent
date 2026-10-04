import pathlib
import unittest
from unittest import mock

from ai_agent.core.llm import stream_runner


class _Target:
    def __init__(self):
        self.calls = 0

    def abort(self):
        self.calls += 1

    def quit(self):
        self.calls += 1


class StreamCancellationTest(unittest.TestCase):
    def test_cancellation_aborts_and_quits_exactly_once(self):
        reply = _Target()
        loop = _Target()
        cancellation = stream_runner._StreamCancellation(reply, loop)

        cancellation.cancel()
        cancellation.cancel()

        self.assertTrue(cancellation.cancelled)
        self.assertEqual(reply.calls, 1)
        self.assertEqual(loop.calls, 1)

    def test_feedback_connection_is_explicitly_queued(self):
        source = pathlib.Path(stream_runner.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "feedback.canceled.connect(cancellation.cancel, _queued_connection())",
            source,
        )
        self.assertIn("Qt.ConnectionType.QueuedConnection", source)
        self.assertNotIn("except AttributeError", source.split("def _queued_connection")[1].split("def ")[0])


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot, *args):
        self.slots.append(slot)

    def disconnect(self):
        self.slots = []

    def emit(self):
        for slot in list(self.slots):
            slot()


class _Reply:
    def __init__(self):
        self.readyRead = _Signal()
        self.finished = _Signal()
        self.deleted = False

    def readAll(self):
        if self.deleted:
            raise RuntimeError("wrapped C/C++ object of type QNetworkReply has been deleted")
        return b""

    def isFinished(self):
        return True

    def attribute(self, _name):
        return 200

    def error(self):
        return 0

    def rawHeader(self, _name):
        return b""

    def deleteLater(self):
        self.deleted = True


class _Completion:
    finished = True

    def take(self, _event):
        pass

    def response(self):
        return {}


class StreamTeardownTest(unittest.TestCase):
    def test_a_late_ready_read_after_delete_later_is_ignored(self):
        reply = _Reply()
        manager = mock.Mock()
        manager.instance.return_value.post.return_value = reply
        stolen = []
        original = reply.readyRead.connect
        reply.readyRead.connect = lambda slot, *args: (stolen.append(slot), original(slot, *args))
        with (
            mock.patch.object(stream_runner, "QgsNetworkAccessManager", manager),
            mock.patch.object(stream_runner, "build_network_request", return_value=object()),
        ):
            stream_runner.post_stream("http://localhost:1/v1", {}, {}, _Completion(), 5)
        self.assertEqual((reply.readyRead.slots, reply.finished.slots), ([], []))
        for slot in stolen:
            slot()  # Qt may still deliver one queued readyRead while it tears the reply down


if __name__ == "__main__":
    unittest.main()
