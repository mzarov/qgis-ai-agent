import faulthandler
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from unittest import mock
from urllib.parse import parse_qs

from qgis.core import QgsApplication, QgsFeedback, QgsNetworkAccessManager, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, pyqtSlot
from qgis.PyQt.QtWidgets import QLabel, QWidget

from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.agent.turn_thread import TurnThreadOwner
from ai_agent.core.llm.client import ApiResponseError, ModelTimeout, post_json
from ai_agent.core.llm.stream import StreamedCompletion
from ai_agent.core.llm.stream_runner import post_stream
from ai_agent.core.llm.transport import call_model
from ai_agent.core.llm.turns import ToolCall
from ai_agent.core.llm.worker import ModelTurnThread

WAIT_MS = 3000
SERVER_HOLD_SECONDS = 4
MESSAGES = [{"role": "user", "content": "Local integration test"}]
SCHEMAS = [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}]
STRESS_S = 3
HANG_GUARD_S = 120
LABELS = 20
NAP_S = 0.0005
STREAM_WORKERS = 6
JSON_HEADERS = {"Content-Type": "application/json"}
QGIS_TIMEOUT_MS = 1000
QUIET_S = 2.5


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
        if self.path.startswith("/quiet/"):
            time.sleep(QUIET_S)
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

    @pyqtSlot(object)
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


class QgisNetworkTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.server = _Server()
        self.addCleanup(self.server.close)
        self.addCleanup(QgsNetworkAccessManager.setTimeout, QgsNetworkAccessManager.timeout())
        QgsNetworkAccessManager.setTimeout(QGIS_TIMEOUT_MS)

    def test_a_stream_quiet_past_the_qgis_timeout_still_gets_its_answer(self):
        data = post_stream(self.server.url("/quiet/v1"), JSON_HEADERS, {"stream": True}, StreamedCompletion(), 10)
        self.assertEqual(data["choices"][0]["message"]["content"], "hello world")

    def test_a_tool_less_request_streams_past_the_qgis_timeout(self):
        overrides = {
            "url_override": self.server.url("/quiet"),
            "model_override": "integration-fixture",
            "key_override": "",
            "dialect_override": "openai",
        }
        turn = call_model(MESSAGES, [], overrides=overrides, timeout=10, on_chunk=lambda text: None)
        self.assertEqual(turn.text, "hello world")
        self.assertIs(self.server.requests[-1][1]["stream"], True)

    def test_a_blocking_call_cut_by_the_qgis_timeout_names_that_setting(self):
        started = time.monotonic()
        with self.assertRaises(ModelTimeout) as caught:
            post_json(self.server.url("/quiet/v1"), JSON_HEADERS, {}, timeout=30)
        self.assertLess(time.monotonic() - started, QUIET_S)
        self.assertIn("Network", str(caught.exception))


class _Requester(QThread):
    def __init__(self, send_one, enough):
        super().__init__()
        self._send_one = send_one
        self._enough = enough
        self.sent = 0
        self.errors = []

    def run(self):
        while not self._enough(self.sent):
            try:
                self._send_one()
            except Exception as failure:
                self.errors.append(f"{type(failure).__name__}: {failure}")
                return
            self.sent += 1


def _build_widgets():
    holder = QWidget()
    for index in range(LABELS):
        QLabel(f"label {index}", holder).setStyleSheet(f"padding: {index % 4}px;")
    holder.deleteLater()


def _nap():
    time.sleep(NAP_S)


def _keep_main_thread_busy(worker, chore):
    worker.start()
    while worker.isRunning():
        chore()
        QCoreApplication.processEvents()
    worker.wait()


class WorkerExchangeTest(unittest.TestCase):
    def setUp(self):
        self.server = _Server()
        self.addCleanup(self.server.close)
        # A deadlock freezes the main thread for good: the dump names both threads and ends the run.
        faulthandler.dump_traceback_later(HANG_GUARD_S, exit=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)

    def test_model_requests_in_a_worker_never_lock_up_a_busy_main_thread(self):
        url = self.server.url("/status/200")
        deadline = time.monotonic() + STRESS_S
        worker = _Requester(
            lambda: post_json(url, JSON_HEADERS, {}, timeout=5, feedback=QgsFeedback()),
            lambda sent: time.monotonic() > deadline,
        )
        _keep_main_thread_busy(worker, _build_widgets)
        self.assertEqual(worker.errors, [])
        self.assertGreater(worker.sent, LABELS)

    def test_back_to_back_streams_in_one_worker_keep_their_replies(self):
        url = self.server.url("/success")

        def stream_once():
            post_stream(url, JSON_HEADERS, {"stream": True}, StreamedCompletion(lambda text: None), 5)

        for _ in range(STREAM_WORKERS):
            deadline = time.monotonic() + STRESS_S / STREAM_WORKERS
            worker = _Requester(stream_once, lambda sent, until=deadline: time.monotonic() > until)
            _keep_main_thread_busy(worker, _nap)
            self.assertEqual(worker.errors, [])
            self.assertGreater(worker.sent, LABELS)


OSM_ANSWER = (
    b'<?xml version="1.0" encoding="UTF-8"?><osm version="0.6" generator="fixture">'
    b'<node id="1" lat="55.75" lon="37.62"><tag k="amenity" v="cafe"/><tag k="name" v="One"/></node>'
    b'<node id="2" lat="55.76" lon="37.63"><tag k="amenity" v="cafe"/><tag k="name" v="Two"/></node>'
    b"</osm>"
)
OVERPASS_DELAY_S = 0.6


class _SlowOverpass(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        time.sleep(OVERPASS_DELAY_S)
        self.send_response(200)
        self.send_header("Content-Type", "application/osm3s+xml")
        self.send_header("Content-Length", str(len(OSM_ANSWER)))
        self.end_headers()
        self.wfile.write(OSM_ANSWER)

    def log_message(self, format, *args):
        pass


class DownloadInBackgroundTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowOverpass)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_the_main_thread_keeps_running_while_overpass_answers(self):
        from unittest import mock

        from qgis.core import QgsProject

        from ai_agent.core.agent.batch import WriteBatch
        from ai_agent.core.agent.executor import ToolExecutor
        from ai_agent.core.llm.turns import ToolCall

        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/interpreter"
        query = "[out:xml];node[amenity=cafe](55.7,37.6,55.8,37.7);out body;"
        arguments = {"intent": "cafes in a corner of Moscow", "query": query, "name": "Cafes", "geometry": "points"}
        ticks, ended = [], []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        with mock.patch("ai_agent.qgis_tools.osm.run_overpass.endpoint", return_value=url):
            batch = WriteBatch(ToolExecutor())
            batch.add(ToolCall("overpass", "run_overpass", arguments))
            timer.start()
            batch.apply(lambda call: None, lambda call, result: None, done=ended.append)
            self.assertTrue(_wait_until(lambda: bool(ended), 20000), "the download never ended")
            timer.stop()
        self.addCleanup(QgsProject.instance().clear)
        result = ended[0][0]
        self.assertTrue(result.ok, result.payload)
        self.assertEqual(result.payload["total_features"], 2)
        self.assertGreater(len(ticks), 10, "the main thread was blocked while Overpass answered")


class _RecordingOverpass(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.forms.append(parse_qs(body.decode("utf-8")))
        self.send_response(200)
        self.send_header("Content-Type", "application/osm3s+xml")
        self.send_header("Content-Length", str(len(self.server.answer)))
        self.end_headers()
        self.wfile.write(self.server.answer)

    def log_message(self, format, *args):
        pass


class OverpassExchangeTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingOverpass)
        self.server.daemon_threads = True
        self.server.forms, self.server.answer = [], OSM_ANSWER
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(QgsProject.instance().clear)

    def _download(self, query):
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/interpreter"
        arguments = {"intent": "cafes by name", "query": query, "name": "Cafes", "geometry": "points"}
        ended = []
        with mock.patch("ai_agent.qgis_tools.osm.run_overpass.endpoint", return_value=url):
            batch = WriteBatch(ToolExecutor())
            batch.add(ToolCall("overpass", "run_overpass", arguments))
            batch.apply(lambda call: None, lambda call, result: None, done=ended.append)
            self.assertTrue(_wait_until(lambda: bool(ended), 20000), "the download never ended")
        return ended[0][0]

    def test_a_plus_and_an_ampersand_in_a_query_reach_overpass(self):
        query = '[out:xml];node["name"~"A+B&C"](55.7,37.6,55.8,37.7);out body;'
        result = self._download(query)
        self.assertTrue(result.ok, result.payload)
        self.assertEqual(self.server.forms, [{"data": [query]}])

    def test_an_answer_overpass_broke_off_loads_no_layer(self):
        self.server.answer = OSM_ANSWER.replace(
            b"</osm>", b"<remark> runtime error: Query timed out in &quot;query&quot; at line 1. </remark></osm>"
        )
        result = self._download("[out:xml];node[amenity=cafe](55.7,37.6,55.8,37.7);out body;")
        self.assertFalse(result.ok)
        self.assertIn('Query timed out in "query" at line 1.', result.payload["error"])
        self.assertEqual(QgsProject.instance().mapLayersByName("Cafes"), [], "a partial answer became a layer")
