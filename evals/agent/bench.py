"""Running the agent bench: its promptfoo config and the QGIS server the config talks to.

The suite's provider is promptfoo's HTTP provider pointed at evals/agent/server.py.
evals/run.py --agent starts that server in the pinned QGIS image (the one the
ui-pixels job uses), waits until QGIS and the plugin are up, runs the tasks one
at a time and stops it. The model settings reach the container as environment
variables named on the docker command line without values, so a key is never
written into a file or a command.
"""

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = "agent"
TASKS = HERE / "tasks.yaml"
PORT = 8765
QGIS_IMAGE = "qgis/qgis@sha256:23c12670e69909e8659a5c098aa307996735a5763b9ff9c3268bdeeee1a10916"  # 4.0-trixie
CONTAINER = "ai-agent-eval-server"
READY_TIMEOUT_S = 900
POLL_S = 3
# A task is a whole agent run with its check after Apply: minutes, not seconds.
REQUEST_TIMEOUT_MS = 900_000
PASSED_ENV = ("EVAL_API_URL", "EVAL_MODEL", "EVAL_API_KEY", "EVAL_AUTH", "EVAL_DIALECT", "EVAL_RUN_TOKENS")
# The server's whole answer is the output the check reads; its usage feeds promptfoo's token columns,
# and a server failure is an error (not reached), not a failed task.
TRANSFORM = (
    "({output: JSON.stringify(json),"
    " error: json.error ? String(json.error).trim().split('\\n').slice(-3).join(' | ') : undefined,"
    " tokenUsage: {prompt: (json.usage || {}).prompt_tokens || 0,"
    " completion: (json.usage || {}).completion_tokens || 0,"
    " total: ((json.usage || {}).prompt_tokens || 0) + ((json.usage || {}).completion_tokens || 0)}})"
)


def write_config(out: Path, model: str, server: str) -> Path:
    config = {
        "description": "AI Agent agent evals",
        "prompts": [{"raw": "{{request}}", "label": "task"}],
        "providers": [
            {
                "id": "http",
                "label": model,
                "config": {
                    "url": f"{server.rstrip('/')}/run",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"request": "{{request}}"},
                    "maxRetries": 0,
                    "transformResponse": TRANSFORM,
                },
            }
        ],
        "defaultTest": {"assert": [{"type": "python", "value": f"file://{HERE / 'outcome.py'}:outcome"}]},
        "tests": f"file://{TASKS}",
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{AGENT}.config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def start_server(repo: Path, port: int = PORT) -> None:
    command = ["docker", "run", "-d", "--rm", "--name", CONTAINER, "--platform", "linux/amd64"]
    command += ["-p", f"127.0.0.1:{port}:{PORT}", "-v", f"{repo}:/repo", "-w", "/repo"]
    command += ["-e", "QT_QPA_PLATFORM=offscreen"]
    for name in PASSED_ENV:
        command += ["-e", name]
    command += [QGIS_IMAGE, "python3", "evals/agent/server.py", "--port", str(PORT)]
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, check=False)
    subprocess.run(command, check=True, capture_output=True, text=True)


def wait_ready(server: str, timeout_s: float = READY_TIMEOUT_S) -> bool:
    """True once the server says QGIS and the plugin are up; False when it never does."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{server.rstrip('/')}/health", timeout=5) as response:  # nosec B310 - localhost
                if json.loads(response.read() or b"{}").get("ready"):
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(POLL_S)
    return False


def stop_server(out: Path) -> None:
    """Keep the server's log beside the results, then stop it."""
    logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True, check=False)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agent-server.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
    subprocess.run(["docker", "stop", CONTAINER], capture_output=True, check=False)
