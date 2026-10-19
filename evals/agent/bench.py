import json
import os
import subprocess
import sys
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
REQUEST_TIMEOUT_MS = 900_000
PASSED_ENV = ("EVAL_API_URL", "EVAL_MODEL", "EVAL_API_KEY", "EVAL_AUTH", "EVAL_DIALECT", "EVAL_RUN_TOKENS")
APPLICATIONS = Path("/Applications")
NATIVE = "native"
DOCKER = "docker"
LOG_NAME = "agent-server.log"
TRANSFORM = (
    "({output: JSON.stringify(json),"
    " error: json.error ? String(json.error).trim().split('\\n').slice(-3).join(' | ')"
    " : ((json.failures || []).length ? 'the model provider failed: ' + json.failures.join('; ') : undefined),"
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


def find_qgis_app(applications: Path = APPLICATIONS) -> Path | None:
    found = []
    for app in applications.glob("QGIS*.app"):
        for home in (app / "Contents" / "Resources").glob("python3.*"):
            python = app / "Contents" / "MacOS" / home.name
            if python.is_file() and (home / "site-packages" / "qgis").is_dir():
                found.append((app.stat().st_mtime, app))
    return max(found)[1] if found else None


def native_python(app: Path) -> tuple[Path, dict[str, str]]:
    resources = app / "Contents" / "Resources"
    home = next(path for path in resources.glob("python3.*") if (path / "site-packages" / "qgis").is_dir())
    environment = {
        **os.environ,
        "PYTHONHOME": str(home),
        "PYTHONPATH": os.pathsep.join(str(path) for path in (home, home / "site-packages", home / "lib-dynload")),
        "QT_QPA_PLATFORM": "offscreen",
        "GDAL_DATA": str(resources / "qgis" / "gdal"),
        "PROJ_DATA": str(resources / "qgis" / "proj"),
    }
    return app / "Contents" / "MacOS" / home.name, environment


def default_mode() -> str:
    return NATIVE if sys.platform == "darwin" and find_qgis_app() else DOCKER


def start_native(repo: Path, out: Path, app: Path, port: int = PORT) -> subprocess.Popen:
    python, environment = native_python(app)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / LOG_NAME, "w", encoding="utf-8")  # noqa: SIM115 - the server writes into it while it runs
    command = [str(python), "evals/agent/server.py", "--port", str(port)]
    return subprocess.Popen(command, cwd=repo, env=environment, stdout=log, stderr=subprocess.STDOUT)


def stop_native(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()


def start_server(repo: Path, port: int = PORT) -> None:
    command = ["docker", "run", "-d", "--rm", "--name", CONTAINER, "--platform", "linux/amd64"]
    command += ["-p", f"127.0.0.1:{port}:{PORT}", "-v", f"{repo}:/repo", "-w", "/repo"]
    command += ["-e", "QT_QPA_PLATFORM=offscreen"]
    # Names only: docker takes the values from the environment, so a key never lands in a command.
    for name in PASSED_ENV:
        command += ["-e", name]
    command += [QGIS_IMAGE, "python3", "evals/agent/server.py", "--port", str(PORT)]
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, check=False)
    subprocess.run(command, check=True, capture_output=True, text=True)


def wait_ready(server: str, timeout_s: float = READY_TIMEOUT_S) -> bool:
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
    logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True, check=False)
    out.mkdir(parents=True, exist_ok=True)
    (out / LOG_NAME).write_text(logs.stdout + logs.stderr, encoding="utf-8")
    subprocess.run(["docker", "stop", CONTAINER], capture_output=True, check=False)
