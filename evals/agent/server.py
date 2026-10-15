"""The agent bench's provider: the whole plugin in a headless QGIS, one task per HTTP request.

promptfoo posts a task — `{"request": "..."}` — to `/run`. The server builds the
fixture project in a fresh folder, starts the plugin, sends the request the way
the composer does, presses Apply for every prepared batch (destructive steps are
confirmed), waits for the check after Apply, and answers with what happened: the
final answer, the tools that ran, the skills, tokens, requests and seconds, and
a snapshot of the project (state.py). A question the agent asks ends the task.

Qt and PyQGIS live on the main thread, so the HTTP server only queues tasks; the
main thread runs them between rounds of event processing.

Before the first task the server asks the model about a picture, as the
connection test in the settings does, so a model that cannot see one checks
its work by reading, as it would for a user.

The model comes from the environment, like the skill bench: EVAL_API_URL,
EVAL_MODEL, EVAL_API_KEY (kept in the throwaway profile's authentication
database), EVAL_AUTH, EVAL_DIALECT. Run inside QGIS's Python — evals/run.py
starts it in the pinned QGIS image:

    python3 evals/agent/server.py [--port 8765]
"""

import argparse
import importlib
import json
import os
import pathlib
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path[:0] = [str(HERE), str(REPO / "tests")]

import qgis  # noqa: E402
from qgis.core import QgsApplication, QgsMessageLog, QgsProject  # noqa: E402
from real_qgis_smoke import _build_and_extract, qgis_application  # noqa: E402

PORT = 8765
TASK_TIMEOUT_S = 600
SETTLE_S = 1.0
MAX_APPLIES = 4
RUN_TOKENS = int(os.environ.get("EVAL_RUN_TOKENS") or 200_000)
# Only unlocks the throwaway authentication database of the server's temporary profile.
PROFILE_MASTER_PASSWORD = "ai-agent-eval-profile"  # pragma: allowlist secret
FOLDER_MARKER = "{folder}"
LOG_TAG = "AI Agent"
LOG_LINES = 20
# A busy or flaky provider can drop the one picture request; an unknown answer would leave the
# picture tools on for a model that may not see, so one more try before giving up.
IMAGE_PROBE_TRIES = 2
FAILURE_ROLE = "failure"
TASKS: "queue.Queue[Task]" = queue.Queue()
READY = threading.Event()


class Task:
    def __init__(self, body: dict[str, Any]):
        self.body = body
        self.result: dict[str, Any] = {}
        self.done = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self._send(404, {"error": "not found"})
            return
        self._send(200, {"ready": READY.is_set(), "model": os.environ.get("EVAL_MODEL", "")})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, {"error": "the body is not JSON"})
            return
        task = Task(body)
        TASKS.put(task)
        if not task.done.wait(TASK_TIMEOUT_S + 60):
            self._send(504, {"error": "the task did not finish in time"})
            return
        self._send(200, task.result)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


class Runner:
    """Runs one task at a time on the main thread, with the plugin installed from the built zip."""

    def __init__(
        self,
        url: str,
        model: str,
        key: str = "",
        auth: str = "Bearer",
        dialect: str = "openai",
        check_images: bool = True,
    ) -> None:
        import e2e_harness
        import fixture
        import state

        from ai_agent.core import settings
        from ai_agent.core.agent.request import build_overrides
        from ai_agent.core.llm.probe import sees_images
        from ai_agent.plugin import QgisAiAgentPlugin

        self.harness, self.fixture, self.state, self.settings = e2e_harness, fixture, state, settings
        self.build_overrides, self.probe_images = build_overrides, sees_images
        # None until asked, and after an answer that never came; a scripted model has no picture turn.
        self.sees_images: bool | None = None
        self._images_pending = check_images
        self.plugin_class = QgisAiAgentPlugin
        self.url, self.model, self.key = url, model, key
        self.auth = auth or "Bearer"
        self.dialect = dialect or "openai"
        manager = QgsApplication.authManager()
        if not manager.masterPasswordIsSet():
            manager.setMasterPassword(PROFILE_MASTER_PASSWORD, True)
        self.log: list[str] = []
        _record_plugin_log(self.log)

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        folder = tempfile.mkdtemp(prefix="ai-agent-eval-")
        plugin = None
        saved = self._saved_settings()
        try:
            self.fixture.build(folder)
            before = self.state.files(folder)
            self._configure()
            plugin = self._start_plugin()
            return self._drive(plugin, str(body.get("request") or "").replace(FOLDER_MARKER, folder), folder, before)
        except Exception:
            return {"error": traceback.format_exc()}
        finally:
            if plugin is not None:
                plugin.unload()
            QgsProject.instance().clear()
            self.harness.pump(0.2)
            shutil.rmtree(folder, ignore_errors=True)
            self._restore_settings(saved)

    def _saved_settings(self) -> dict[str, Any]:
        """What a task changes in the profile, so it can be put back: a shared test profile stays as it was."""
        settings = self.settings
        return {
            "api_url": settings.get_api_url(),
            "model": settings.get_model(),
            "dialect": settings.get_dialect(),
            "auth_type": settings.get_auth_type(),
            "token_budget": settings.get_token_budget(),
            "verify_after_apply": settings.get_verify_after_apply(),
            "work_mode": settings.get_work_mode(),
        }

    def _restore_settings(self, saved: dict[str, Any]) -> None:
        settings = self.settings
        settings.set_api_url(saved["api_url"])
        settings.set_model(saved["model"])
        settings.set_dialect(saved["dialect"])
        settings.set_auth_type(saved["auth_type"])
        settings.set_token_budget(saved["token_budget"])
        settings.set_verify_after_apply(saved["verify_after_apply"])
        settings.set_work_mode(saved["work_mode"])

    def _configure(self) -> None:
        settings = self.settings
        settings.set_api_url(self.url)
        settings.set_model(self.model)
        settings.set_dialect(self.dialect)
        settings.set_auth_type(self.auth)
        settings.reset_capabilities(self.url, self.model, self.dialect)
        if self.key:
            settings.set_api_key(self.key, self.url, self.dialect)
        settings.set_data_sharing_consent(True, self.url)
        settings.set_token_budget(RUN_TOKENS)
        settings.set_verify_after_apply(True)
        settings.set_work_mode("ask")
        self._check_images()

    def _check_images(self) -> None:
        """Ask once per server, then restore it after every task's reset, like a tested connection."""
        if self._images_pending:
            self._images_pending = False
            for _ in range(IMAGE_PROBE_TRIES):
                self.sees_images = self.probe_images(self.build_overrides())
                if self.sees_images is not None:
                    break
            print(f"Sees pictures: {self.sees_images}", flush=True)
        if self.sees_images is not None:
            self.settings.set_supports_images(self.url, self.sees_images, self.model, self.dialect)

    def _start_plugin(self) -> Any:
        interface = self.harness._Interface()
        interface.window.resize(self.harness.WINDOW_WIDTH, self.harness.WINDOW_HEIGHT)
        interface.window.show()
        plugin = self.plugin_class(interface)
        plugin.initGui()
        plugin.run()
        # The task asked for the change; the bench stands in for the person who confirms it.
        plugin.dock_widget.confirm_destructive = lambda lines, details="": True
        plugin._orchestrator.on_new_session()
        return plugin

    def _drive(self, plugin: Any, request: str, folder: str, before: set[str]) -> dict[str, Any]:
        orchestrator = plugin._orchestrator
        agent = orchestrator.agent
        calls: list[dict[str, Any]] = []
        agent.tool_finished.connect(lambda name, ok, note: calls.append({"name": name, "ok": bool(ok)}))
        self.log.clear()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0, "runs": 0}
        start = agent.start

        def counted_start(*args: Any, **kwargs: Any) -> bool:
            previous = dict(agent.usage)
            started = start(*args, **kwargs)
            if started:
                if usage["runs"]:
                    _add(usage, previous)
                usage["runs"] += 1
            return started

        agent.start = counted_start
        began = time.monotonic()
        deadline = began + TASK_TIMEOUT_S
        orchestrator.on_prompt(request)
        self._wait(orchestrator, deadline)
        for _ in range(MAX_APPLIES):
            if not agent.has_pending_writes or time.monotonic() > deadline:
                break
            orchestrator.on_confirm_plan()
            self._wait(orchestrator, deadline)
        _add(usage, dict(agent.usage))
        messages = orchestrator.conversation.messages
        answers = [str(m["content"]) for m in messages if m.get("role") == "assistant"]
        failures = [_failure(m.get("content")) for m in messages if m.get("role") == FAILURE_ROLE]
        return {
            "failures": failures,
            "log": self.log[-LOG_LINES:],
            "answer": answers[-1] if answers else "",
            "asked": bool(agent.is_awaiting_answer),
            "pending": bool(agent.has_pending_writes),
            "timed_out": time.monotonic() > deadline,
            "calls": calls,
            "skills": list(agent.loaded_skills),
            "sees_images": self.sees_images,
            "usage": usage,
            "seconds": round(time.monotonic() - began, 1),
            "state": self._state(folder, before),
        }

    def _state(self, folder: str, before: set[str]) -> dict[str, Any]:
        snapshot = self.state.snapshot(folder, before)
        layers = snapshot["layers"]
        snapshot["new_layers"] = [
            {"name": name, **layer} for name, layer in layers.items() if name not in self.fixture.LAYER_NAMES
        ]
        return snapshot

    def _wait(self, orchestrator: Any, deadline: float) -> None:
        agent = orchestrator.agent
        quiet_since = None
        while time.monotonic() < deadline:
            self.harness.process()
            busy = agent.is_running or bool(getattr(agent, "is_applying", False)) or orchestrator.compaction.is_running
            if busy:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= SETTLE_S:
                return
            time.sleep(0.01)


def _progress(body: dict[str, Any], result: dict[str, Any], seconds: float) -> str:
    """One line per task in the server's log: what was asked, how it ended, at what cost."""
    usage = result.get("usage") or {}
    ending = "server error" if result.get("error") else ("asked a question" if result.get("asked") else "done")
    request = " ".join(str(body.get("request") or "").split())[:70]
    return f"{request} → {ending} in {seconds:.0f} s, {usage.get('requests', 0)} requests"


def _record_plugin_log(lines: list[str]) -> None:
    """Keep the plugin's log lines for the task's answer.

    The message log's own signal stays silent in a QGIS without its main
    window, so the call itself is wrapped; every message still reaches QGIS.
    """
    original = QgsMessageLog.logMessage

    def recording(message: str, tag: str = "", *args: Any, **kwargs: Any) -> Any:
        if tag == LOG_TAG:
            lines.append(str(message))
        return original(message, tag, *args, **kwargs)

    QgsMessageLog.logMessage = staticmethod(recording)


def _failure(content: Any) -> str:
    """A kept failure card as one line: its title and the server's own words."""
    try:
        record = json.loads(content)
    except (TypeError, ValueError):
        return str(content)
    return f"{record.get('title', '')}: {record.get('message', '')}".strip(": ")


def _add(total: dict[str, int], run: dict[str, Any]) -> None:
    for key in ("prompt_tokens", "completion_tokens", "requests"):
        total[key] += int(run.get(key) or 0)


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # nosec B104 - a container port, published to localhost
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="ai-agent-eval-server-") as temporary:
        root = pathlib.Path(temporary)
        package = _build_and_extract(root)
        sys.path.insert(0, os.fspath(package.parent))
        with qgis_application(root):
            for candidate in (
                pathlib.Path(QgsApplication.pkgDataPath()) / "python" / "plugins",
                pathlib.Path(qgis.__file__).resolve().parent.parent / "plugins",
            ):
                if candidate.is_dir():
                    sys.path.append(os.fspath(candidate))
            importlib.import_module("processing.core.Processing").Processing.initialize()
            runner = Runner(
                os.environ.get("EVAL_API_URL", "").strip(),
                os.environ.get("EVAL_MODEL", "").strip(),
                os.environ.get("EVAL_API_KEY", "").strip(),
                os.environ.get("EVAL_AUTH", "").strip(),
                os.environ.get("EVAL_DIALECT", "").strip(),
            )
            READY.set()
            print(f"Agent bench server ready on port {port}, model {runner.model}", flush=True)
            while True:
                runner.harness.process()
                try:
                    task = TASKS.get(timeout=0.05)
                except queue.Empty:
                    continue
                began = time.monotonic()
                task.result = runner.run(task.body)
                print(_progress(task.body, task.result, time.monotonic() - began), flush=True)
                task.done.set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the agent bench: one task per POST /run.")
    parser.add_argument("--port", type=int, default=PORT)
    serve(parser.parse_args().port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
