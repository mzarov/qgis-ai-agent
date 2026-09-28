import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, pyqtSlot

from ai_agent.core.agent.turn_thread import TurnThreadOwner
from ai_agent.core.llm.client import ApiResponseError, post_json
from ai_agent.core.llm.worker import ModelTurnThread

WAIT_MS = 3000
SERVER_HOLD_SECONDS = 4
MESSAGES = [{"role": "user", "content": "Local integration test"}]
SCHEMAS = [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}]


def _event(delta, finish_reason=None):
    payload = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
    return f"data: {json.dumps(payload)}\n\n".encode()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append((self.path, json.loads(raw)))
        if self.path.startswith("/status/"):
            status = int(self.path.rsplit("/", 1)[1])
            content = json.dumps({"error": {"message": f"fixture-{status}"}}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(_event({"content": "hello"}))
            self.wfile.flush()
            if self.path.startswith("/hold/"):
                self.server.release.wait(SERVER_HOLD_SECONDS)
            self.wfile.write(_event({"content": " world"}, "stop"))
            self.wfile.write(b'data: {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}\n\n')
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.release = threading.Event()
        self.requests = []
        self.runner = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.runner.start()

    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def url(self, path):
        return f"http://127.0.0.1:{self.server_port}{path}"

    def close(self):
        self.release.set()
        self.shutdown()
        self.server_close()
        self.runner.join(timeout=1)


class _Observer(QObject):
    def __init__(self):
        super().__init__()
        self.chunks = []
        self.turns = []
        self.errors = []
        self.finished = False
        self.main_thread_callbacks = []
        self.chunk_action = None

    def _record_thread(self):
        self.main_thread_callbacks.append(QThread.currentThread() == QgsApplication.instance().thread())

    @pyqtSlot(str)
    def on_chunk(self, text):
        self._record_thread()
        self.chunks.append(text)
        if self.chunk_action is not None:
            action, self.chunk_action = self.chunk_action, None
            action()

    @pyqtSlot(object)
    def on_turn(self, turn):
        self._record_thread()
        self.turns.append(turn)

    @pyqtSlot(str)
    def on_error(self, message):
        self._record_thread()
        self.errors.append(message)

    @pyqtSlot()
    def on_finished(self):
        self._record_thread()
        self.finished = True


def _wait_until(predicate, timeout_ms=WAIT_MS):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout_ms)
    if not predicate():
        loop.exec()
    poll.stop()
    deadline.stop()
    QCoreApplication.processEvents()
    return predicate()


class RealNetworkTest(unittest.TestCase):
    def setUp(self):
        self.server = _Server()
        self.addCleanup(self.server.close)

    def _overrides(self, mode):
        return {
            "url_override": self.server.url(f"/{mode}"),
            "model_override": "integration-fixture",
            "key_override": "",
            "auth_type_override": "Bearer",
            "dialect_override": "openai",
            "verify_override": True,
        }

    def _cleanup_worker(self, worker):
        self.server.release.set()
        try:
            if worker.isRunning():
                worker.cancel()
                worker.wait(WAIT_MS)
        except RuntimeError:
            pass
        QCoreApplication.processEvents()

    def _worker(self, observer, mode):
        worker = ModelTurnThread(MESSAGES, SCHEMAS, self._overrides(mode), timeout=2)
        worker.chunk.connect(observer.on_chunk)
        worker.finished_turn.connect(observer.on_turn)
        worker.error.connect(observer.on_error)
        worker.finished.connect(observer.on_finished)
        self.addCleanup(self._cleanup_worker, worker)
        return worker

    def _owner(self, observer):
        owner = TurnThreadOwner()
        callbacks = (observer.on_turn, observer.on_error, observer.on_chunk)
        owner.start(MESSAGES, SCHEMAS, self._overrides("hold"), *callbacks)
        worker = owner._thread
        worker.finished.connect(observer.on_finished)
        self.addCleanup(self._cleanup_worker, worker)
        return owner, callbacks

    def test_blocking_http_preserves_actual_api_errors(self):
        for status in (400, 401, 429, 503):
            with self.subTest(status=status):
                with self.assertRaises(ApiResponseError) as caught:
                    post_json(
                        self.server.url(f"/status/{status}"),
                        {"Content-Type": "application/json"},
                        {"fixture": True},
                        timeout=2,
                    )
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(json.loads(caught.exception.body)["error"]["message"], f"fixture-{status}")
        self.assertEqual(len(self.server.requests), 4)

    def test_model_worker_streams_and_delivers_signals_on_the_main_thread(self):
        observer = _Observer()
        worker = self._worker(observer, "success")
        worker.start()
        self.assertTrue(_wait_until(lambda: observer.finished), "Model worker did not finish")
        self.assertTrue(worker.wait(100))
        self.assertEqual(observer.errors, [])
        self.assertEqual("".join(observer.chunks), "hello world")
        self.assertEqual(len(observer.turns), 1)
        self.assertEqual(observer.turns[0].text, "hello world")
        self.assertEqual((observer.turns[0].input_tokens, observer.turns[0].output_tokens), (7, 2))
        self.assertTrue(all(observer.main_thread_callbacks))
        self.assertEqual(len(self.server.requests), 1)
        self.assertIs(self.server.requests[0][1]["stream"], True)

    def test_cancel_interrupts_a_waiting_stream_without_delivering_a_final_turn(self):
        observer = _Observer()
        worker = self._worker(observer, "hold")
        observer.chunk_action = worker.cancel
        worker.start()
        self.assertTrue(_wait_until(lambda: observer.finished), "Cancellation did not finish the worker")
        self.assertTrue(worker.wait(100))
        self.assertEqual(observer.chunks, ["hello"])
        self.assertEqual(observer.turns, [])
        self.assertEqual(observer.errors, [])
        self.assertFalse(self.server.release.is_set())
        self.assertTrue(all(observer.main_thread_callbacks))
        self.assertEqual(len(self.server.requests), 1)

    def test_detach_retires_the_worker_until_queued_finished_is_delivered(self):
        observer = _Observer()
        owner, callbacks = self._owner(observer)
        observer.chunk_action = lambda: owner.detach(*callbacks)
        self.assertTrue(_wait_until(lambda: observer.finished), "Detached worker did not finish")
        self.assertTrue(_wait_until(lambda: not owner._retired), "Detached worker is still retained")
        self.assertFalse(owner.is_running)
        self.assertIsNone(owner._thread)
        self.assertEqual(observer.chunks, ["hello"])
        self.assertEqual(observer.turns, [])
        self.assertEqual(observer.errors, [])
        self.assertFalse(self.server.release.is_set())
        owner.stop()

    def test_shutdown_stops_an_active_worker_and_can_be_repeated(self):
        observer = _Observer()
        owner, _ = self._owner(observer)
        self.assertTrue(_wait_until(lambda: bool(observer.chunks)), "Streaming never began")
        started = time.monotonic()
        owner.stop()
        self.assertLess(time.monotonic() - started, WAIT_MS / 1000)
        self.assertTrue(_wait_until(lambda: observer.finished), "Stopped worker did not finish")
        self.assertTrue(_wait_until(lambda: not owner._retired), "Stopped worker is still retained")
        self.assertFalse(owner.is_running)
        self.assertIsNone(owner._thread)
        self.assertEqual(observer.turns, [])
        self.assertEqual(observer.errors, [])
        self.assertFalse(self.server.release.is_set())
        owner.stop()
