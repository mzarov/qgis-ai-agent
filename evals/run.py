import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import context as agent_request  # noqa: E402
import thresholds  # noqa: E402
from agent import bench  # noqa: E402

REPO = agent_request.REPO
EVALS = REPO / "evals"
SKILLS = REPO / "ai_agent" / "skills"
OUT = REPO / "build" / "evals"
ROUTING = "routing"
ROUTING_CASES = EVALS / "routing.yaml"
CASES = "evals/cases.yaml"
PROMPTFOO = "promptfoo@0.124.1"
KEY_VARIABLE = "EVAL_API_KEY"
BEARER = "Bearer"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_CONCURRENCY = 2
# A slow gateway answers in minutes, and a case may ask it up to four times.
PROVIDER_TIMEOUT_MS = 30 * 60 * 1000
MAX_TOKENS = 4096
FAILURE_ERROR = 2


def suites() -> dict[str, Path]:
    found = {ROUTING: ROUTING_CASES}
    for cases in sorted(SKILLS.glob(f"*/{CASES}")):
        found[cases.parent.parent.name] = cases
    return found


def write_config(suite: str, cases: Path, models: list[str], url: str, locale: str, auth: str = BEARER) -> Path:
    skill = "" if suite == ROUTING else suite
    OUT.mkdir(parents=True, exist_ok=True)
    tools = OUT / f"{suite}.tools.json"
    tools.write_text(json.dumps(agent_request.tool_schemas(skill), ensure_ascii=False, indent=1), encoding="utf-8")
    keyless = urlsplit(url).hostname in LOCAL_HOSTS and not os.environ.get(KEY_VARIABLE)
    # The key stays in the environment: the provider reads it when it sends, so it never lands on disk.
    provider_config: dict[str, Any] = {
        "url": url,
        "tools": str(tools),
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "key_variable": "" if keyless else KEY_VARIABLE,
        "auth": auth.strip() or BEARER,
        "timeout": PROVIDER_TIMEOUT_MS,
        "workers": MAX_CONCURRENCY,
    }
    config = {
        "description": f"AI Agent skill evals: {suite}",
        "prompts": [{"id": f"file://{EVALS / 'prompt.py'}:build", "label": "agent request"}],
        "providers": [
            {"id": f"file://{EVALS / 'provider.py'}", "label": model, "config": {**provider_config, "model": model}}
            for model in models
        ],
        "defaultTest": {
            "vars": {"skill": skill, "locale": locale},
            "assert": [{"type": "python", "value": f"file://{EVALS / 'checks.py'}:expected"}],
        },
        "tests": f"file://{cases}",
    }
    path = OUT / f"{suite}.config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def run_suite(
    config: Path,
    results: Path,
    repeat: int,
    fresh: bool = False,
    concurrency: int = MAX_CONCURRENCY,
    extra_env: dict[str, str] | None = None,
    progress: bool = False,
    only: str = "",
) -> None:
    command = [
        "npx",
        "--yes",
        PROMPTFOO,
        "eval",
        "--config",
        str(config),
        "--output",
        str(results),
        "--max-concurrency",
        str(concurrency),
        "--repeat",
        str(repeat),
    ]
    if not progress:
        command.append("--no-progress-bar")
    if only:
        command += ["--filter-pattern", only]
    if fresh:
        command.append("--no-cache")
    environment = {
        **os.environ,
        "PROMPTFOO_PYTHON": sys.executable,
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "PROMPTFOO_DISABLE_SHARING": "1",
        "PROMPTFOO_SCHEDULER_QUEUE_TIMEOUT_MS": str(PROVIDER_TIMEOUT_MS),
        **(extra_env or {}),
    }
    subprocess.run(command, cwd=REPO, env=environment, check=False)


def key_problem(key: str) -> str:
    position = next((index for index, character in enumerate(key) if not character.isascii()), None)
    if position is None:
        return ""
    return (
        f"{KEY_VARIABLE} has a non-Latin character at position {position + 1}: an HTTP header cannot carry it. "
        "Was the key typed with a Cyrillic keyboard layout? Paste it, or switch the layout and enter it again."
    )


def summarise(suite: str, results: Path) -> dict[str, Any]:
    if not results.is_file():
        return {
            "suite": suite,
            "passed": 0,
            "total": 0,
            "errors": 0,
            "first_error": "",
            "tokens": 0,
            "latency": 0.0,
            "failures": ["no results"],
        }
    data = json.loads(results.read_text(encoding="utf-8"))
    rows = (data.get("results") or {}).get("results") or []
    passed = sum(1 for row in rows if row.get("success"))
    errors = [str(row.get("error") or "") for row in rows if _unreached(row)]
    tokens = sum(int(((row.get("response") or {}).get("tokenUsage") or {}).get("total") or 0) for row in rows)
    latency = sum(float(row.get("latencyMs") or 0) for row in rows) / max(1, len(rows)) / 1000
    failures = []
    for row in rows:
        if row.get("success"):
            continue
        case = (row.get("testCase") or {}).get("description") or (row.get("vars") or {}).get("request") or "?"
        model = (row.get("provider") or {}).get("label") or ""
        reason = (row.get("gradingResult") or {}).get("reason") or row.get("error") or ""
        failures.append(f"{case} [{model}]: {reason}")
    return {
        "suite": suite,
        "passed": passed,
        "total": len(rows),
        "errors": len(errors),
        "first_error": errors[0] if errors else "",
        "tokens": tokens,
        "latency": latency,
        "failures": failures,
    }


def _unreached(row: dict[str, Any]) -> bool:
    if row.get("success"):
        return False
    reason = row.get("failureReason")
    if reason is not None:
        return reason == FAILURE_ERROR
    return bool(row.get("error")) and not row.get("gradingResult")


def report(rows: list[dict[str, Any]]) -> str:
    lines = ["| suite | passed | not reached | tokens | mean latency |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        graded = row["total"] - row["errors"]
        lines.append(
            f"| {row['suite']} | {row['passed']}/{graded} | {row['errors']} | {row['tokens']:,} "
            f"| {row['latency']:.1f} s |"
        )
    passed = sum(row["passed"] for row in rows)
    graded = sum(row["total"] - row["errors"] for row in rows)
    errors = sum(row["errors"] for row in rows)
    lines.append(f"| **all** | **{passed}/{graded}** | {errors} | {sum(row['tokens'] for row in rows):,} | |")
    for row in rows:
        if row["failures"]:
            lines.append(f"\n### {row['suite']}: failed\n")
            lines.extend(f"- {failure}" for failure in row["failures"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the skill evals through promptfoo.")
    parser.add_argument("--suites", default="", help="comma-separated suites (default: all)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case, for a pass rate")
    parser.add_argument("--fresh", action="store_true", help="ask the model again even for cached requests")
    parser.add_argument("--configs-only", action="store_true", help="write the configs and stop")
    parser.add_argument("--check", action="store_true", help="fail when a suite falls below its floor")
    parser.add_argument("--save-thresholds", action="store_true", help="set the floors from this run")
    parser.add_argument("--only", default="", help="run only the cases whose description matches this pattern")
    parser.add_argument("--agent", action="store_true", help="run the agent bench (whole tasks in QGIS) instead")
    parser.add_argument("--agent-url", default="", help="an agent bench server already running; else one is started")
    parser.add_argument(
        "--agent-server",
        choices=[bench.NATIVE, bench.DOCKER],
        default="",
        help="start the server in an installed QGIS (macOS) or in Docker; default: native when QGIS 4 is installed",
    )
    options = parser.parse_args()
    url = os.environ.get("EVAL_API_URL", "").strip()
    models = [name.strip() for name in os.environ.get("EVAL_MODEL", "").split(",") if name.strip()]
    if not options.configs_only and (not url or not models):
        print("Set EVAL_API_URL and EVAL_MODEL (and EVAL_API_KEY for a non-local endpoint).", file=sys.stderr)
        return 2
    problem = key_problem(os.environ.get(KEY_VARIABLE, ""))
    if problem and not options.configs_only:
        print(problem, file=sys.stderr)
        return 2
    if options.agent:
        if options.configs_only:
            print(
                bench.write_config(OUT, (models or ["model"])[0], options.agent_url or f"http://127.0.0.1:{bench.PORT}")
            )
            return 0
        if len(models) != 1:
            print("The agent bench runs one model at a time: set one model in EVAL_MODEL.", file=sys.stderr)
            return 2
        rows = run_agent(models[0], options.agent_url, max(1, options.repeat), options.agent_server, options.only)
        if rows is None:
            return 2
        return finish(rows, models, options)
    available = suites()
    chosen = [name.strip() for name in options.suites.split(",") if name.strip()] or list(available)
    unknown = [name for name in chosen if name not in available]
    if unknown:
        print(f"Unknown suites: {', '.join(unknown)}. Known: {', '.join(available)}", file=sys.stderr)
        return 2
    locale = os.environ.get("EVAL_LOCALE", "en").strip() or "en"
    rows = []
    for suite in chosen:
        auth = os.environ.get("EVAL_AUTH", BEARER)
        config = write_config(suite, available[suite], models or ["model"], url or "http://localhost/v1", locale, auth)
        if options.configs_only:
            print(config)
            continue
        results = OUT / f"{suite}.results.json"
        results.unlink(missing_ok=True)
        run_suite(config, results, max(1, options.repeat), options.fresh, only=options.only)
        row = summarise(suite, results)
        rows.append(row)
        if row["total"] and row["errors"] == row["total"]:
            print(f"Every case of {suite} failed to reach the model, stopping: {row['first_error']}", file=sys.stderr)
            break
    return finish(rows, models, options)


def run_agent(model: str, server: str, repeat: int, mode: str = "", only: str = "") -> list[dict[str, Any]] | None:
    started = not server
    server = server or f"http://127.0.0.1:{bench.PORT}"
    mode = mode or bench.default_mode()
    process = None
    if started:
        app = bench.find_qgis_app() if mode == bench.NATIVE else None
        if mode == bench.NATIVE and app is None:
            print("No QGIS 4 app found in /Applications; use --agent-server docker.", file=sys.stderr)
            return None
        print(f"Starting QGIS with the plugin for the agent bench ({app or 'docker'})…", flush=True)
        if app is not None:
            process = bench.start_native(REPO, OUT, app)
        else:
            bench.start_server(REPO)
    try:
        if not bench.wait_ready(server):
            print(
                f"The agent bench server at {server} never became ready; see build/evals/agent-server.log.",
                file=sys.stderr,
            )
            return None
        results = OUT / f"{bench.AGENT}.results.json"
        results.unlink(missing_ok=True)
        config = bench.write_config(OUT, model, server)
        timeout = {"REQUEST_TIMEOUT_MS": str(bench.REQUEST_TIMEOUT_MS)}
        # One task at a time: QGIS runs on one main thread, and a cached run would measure nothing.
        run_suite(config, results, repeat, fresh=True, concurrency=1, extra_env=timeout, progress=True, only=only)
        return [summarise(bench.AGENT, results)]
    finally:
        if process is not None:
            bench.stop_native(process)
        elif started:
            bench.stop_server(OUT)


def floor_verdict(problems: list[str], rows: list[dict[str, Any]], model: str, floors: dict[str, Any]) -> str:
    if problems:
        return "\n".join(f"- {problem}" for problem in problems)
    unchecked = thresholds.unchecked(rows, model, floors)
    if len(unchecked) == len(rows):
        return f"No floors for {model}, nothing checked."
    verdict = "Every suite with a floor is at or above it."
    return f"{verdict} No floor for: {', '.join(unchecked)}." if unchecked else verdict


def finish(rows: list[dict[str, Any]], models: list[str], options: argparse.Namespace) -> int:
    if not rows:
        return 0
    summary = report(rows)
    problems = []
    if options.save_thresholds or options.check:
        if len(models) != 1:
            summary += "\nFloors need exactly one model in EVAL_MODEL; nothing was saved or checked.\n"
        elif options.save_thresholds:
            saved = thresholds.save(rows, models[0])
            summary += f"\nFloors for {models[0]} saved to evals/thresholds.json: {saved['suites']}\n"
        else:
            require = os.environ.get("EVAL_REQUIRE_THRESHOLDS", "") == "1"
            floors = thresholds.load()
            problems = thresholds.check(rows, models[0], floors, require)
            summary += f"\n### Floors\n\n{floor_verdict(problems, rows, models[0], floors)}\n"
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(f"## Skill evals\n\n{summary}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
