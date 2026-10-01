"""A scripted OpenAI-compatible model for end-to-end runs of the whole plugin.

Each test queues the model turns it expects, in order. Every request to
`/v1/chat/completions` takes the next turn and answers it the way a real
provider does: a server-sent-event stream of content deltas, tool-call deltas,
a finish reason, a usage chunk and `[DONE]`; or a plain JSON body when the
plugin did not ask for a stream; or an HTTP error. Requests are kept, so a test
can check what the plugin actually sent — tool schemas, tool results, prompts.

Pure standard library: it runs inside the QGIS Python used by CI.
"""

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

CHUNK_CHARS = 24
USAGE = {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050}


@dataclass
class Turn:
    text: str = ""
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    status: int = 200
    error: str = ""
    chunk_delay: float = 0.0


def say(text: str, chunk_delay: float = 0.0) -> Turn:
    return Turn(text=text, chunk_delay=chunk_delay)


def call(name: str, **arguments: Any) -> Turn:
    return Turn(calls=[(name, arguments)])


def calls(*pairs: tuple[str, dict[str, Any]]) -> Turn:
    return Turn(calls=list(pairs))


def fail(status: int, message: str) -> Turn:
    return Turn(status=status, error=message)


class ScriptedModel:
    def __init__(self) -> None:
        self.turns: deque[Turn] = deque()
        self.requests: list[dict[str, Any]] = []
        self.unexpected: list[str] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(self))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def start(self) -> "ScriptedModel":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def script(self, *turns: Turn) -> None:
        self.turns.extend(turns)

    def take(self, body: dict[str, Any]) -> Turn | None:
        self.requests.append(body)
        if not self.turns:
            self.unexpected.append(json.dumps(body.get("messages", [])[-1:], ensure_ascii=False)[:500])
            return None
        return self.turns.popleft()

    def tool_names(self, request_index: int = -1) -> list[str]:
        tools = self.requests[request_index].get("tools") or []
        return [tool.get("function", {}).get("name", "") for tool in tools]

    def sent_text(self, request_index: int = -1) -> str:
        return json.dumps(self.requests[request_index].get("messages", []), ensure_ascii=False)


def _handler_for(model: ScriptedModel) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            turn = model.take(body)
            if turn is None:
                self._json(500, {"error": {"message": "No scripted turn left for this request."}})
            elif turn.status != 200:
                self._json(turn.status, {"error": {"message": turn.error, "type": "scripted"}})
            elif body.get("stream"):
                self._stream(turn)
            else:
                self._json(200, _completion(turn))

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            content = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _stream(self, turn: Turn) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for chunk in _stream_events(turn):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    if turn.chunk_delay:
                        time.sleep(turn.chunk_delay)
            except (BrokenPipeError, ConnectionResetError):
                return
            self.close_connection = True

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def _event(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _stream_events(turn: Turn) -> list[bytes]:
    events = []
    for start in range(0, len(turn.text), CHUNK_CHARS):
        events.append(_event({"choices": [{"index": 0, "delta": {"content": turn.text[start : start + CHUNK_CHARS]}}]}))
    for index, (name, arguments) in enumerate(turn.calls):
        delta = {
            "tool_calls": [
                {
                    "index": index,
                    "id": f"call_{index}_{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ]
        }
        events.append(_event({"choices": [{"index": 0, "delta": delta}]}))
    finish = "tool_calls" if turn.calls else "stop"
    events.append(_event({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}))
    events.append(_event({"choices": [], "usage": USAGE}))
    events.append(b"data: [DONE]\n\n")
    return events


def _completion(turn: Turn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
    if turn.calls:
        message["tool_calls"] = [
            {
                "id": f"call_{index}_{name}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
            for index, (name, arguments) in enumerate(turn.calls)
        ]
    finish = "tool_calls" if turn.calls else "stop"
    return {"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": USAGE}
