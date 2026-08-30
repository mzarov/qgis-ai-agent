import pathlib
import unittest

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
        self.assertIn("Qt.QueuedConnection", source)


if __name__ == "__main__":
    unittest.main()
