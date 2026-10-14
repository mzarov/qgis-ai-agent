"""Run the skill evals through promptfoo and print what passed, per suite.

A suite is the routing cases (`evals/routing.yaml`: which skills the model loads
for a request) or one skill's cases (`ai_agent/skills/<skill>/evals/cases.yaml`:
with that skill loaded, the model's next call). For each suite this writes the
tool schemas the model would have and a promptfoo config under `build/evals/`,
runs `promptfoo eval`, and sums the results up in `build/evals/summary.md`.

The model is any OpenAI-compatible endpoint:

    EVAL_API_URL   base URL with the API prefix, e.g. https://api.deepseek.com/v1
    EVAL_MODEL     model id; several, comma-separated, are compared side by side
    EVAL_API_KEY   read by promptfoo itself; not needed for a local server
    EVAL_AUTH      the Authorization scheme, as in the plugin's settings (default Bearer, e.g. OAuth)
    EVAL_LOCALE    the UI language the prompt assumes (default en)
    EVAL_REQUIRE_THRESHOLDS  1 fails --check for a suite or model without a floor (CI sets it once floors exist)

    python3 evals/run.py                      # every suite
    python3 evals/run.py --suites routing,style --repeat 3
    python3 evals/run.py --repeat 3 --fresh --save-thresholds   # the floors CI holds a model to
    python3 evals/run.py --check                                # fail below a floor (CI)
    npx promptfoo@<version> view              # the results, case by case

Needs Node for `npx`; the plugin and its tests do not.
"""

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
MAX_TOKENS = 4096
# promptfoo's ResultFailureReason: 1 is a failed assertion, 2 an error before any grading.
FAILURE_ERROR = 2


def suites() -> dict[str, Path]:
    """Every suite and its cases file: routing first, then the skills that have cases."""
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
    provider_config: dict[str, Any] = {
        "apiBaseUrl": url,
        "apiKeyEnvar": KEY_VARIABLE,
        "tools": f"file://{tools}",
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
    }
    if keyless:
        provider_config["apiKeyRequired"] = False
    elif auth.strip().casefold() != BEARER.casefold():
        # The plugin's "Authorization: <type> <key>" for gateways that want OAuth; promptfoo fills the key in
        # from the environment when it sends the request, so it is never written into the config.
        provider_config["headers"] = {"Authorization": f"{auth.strip()} {{{{ env.{KEY_VARIABLE} }}}}"}
    config = {
        "description": f"AI Agent skill evals: {suite}",
        "prompts": [{"id": f"file://{EVALS / 'prompt.py'}:build", "label": "agent request"}],
        "providers": [{"id": f"openai:chat:{model}", "label": model, "config": provider_config} for model in models],
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
        "--no-progress-bar",
    ]
    if fresh:
        command.append("--no-cache")
    environment = {
        **os.environ,
        # The same Python builds the prompts and runs the checks; nothing about the run leaves the machine.
        "PROMPTFOO_PYTHON": sys.executable,
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "PROMPTFOO_DISABLE_SHARING": "1",
        **(extra_env or {}),
    }
    # promptfoo exits non-zero when a case fails; failures are the point of a bench, not an error here.
    subprocess.run(command, cwd=REPO, env=environment, check=False)


def key_problem(key: str) -> str:
    """Why the key cannot go into an HTTP header, or "" — a key typed in a non-Latin layout is the usual case."""
    position = next((index for index, character in enumerate(key) if not character.isascii()), None)
    if position is None:
        return ""
    return (
        f"{KEY_VARIABLE} has a non-Latin character at position {position + 1}: an HTTP header cannot carry it. "
        "Was the key typed with a Cyrillic keyboard layout? Paste it, or switch the layout and enter it again."
    )


def summarise(suite: str, results: Path) -> dict[str, Any]:
    """Passed and total cases, tokens, mean latency and the failures of one suite's run."""
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
    """A case whose request failed before the model answered; promptfoo also fills `error` for a failed check."""
    if row.get("success"):
        return False
    reason = row.get("failureReason")
    if reason is not None:
        return reason == FAILURE_ERROR
    return bool(row.get("error")) and not row.get("gradingResult")


def report(rows: list[dict[str, Any]]) -> str:
    # A case that never reached the model (a timeout, a refused request) says nothing about the skill:
    # it is counted apart, not as a failure.
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
    # promptfoo answers an unchanged request from its cache: right for a suite nobody touched, wrong for
    # measuring how much a model's answers vary.
    parser.add_argument("--fresh", action="store_true", help="ask the model again even for cached requests")
    parser.add_argument("--configs-only", action="store_true", help="write the configs and stop")
    parser.add_argument("--check", action="store_true", help="fail when a suite falls below its floor")
    parser.add_argument("--save-thresholds", action="store_true", help="set the floors from this run")
    parser.add_argument("--agent", action="store_true", help="run the agent bench (whole tasks in QGIS) instead")
    parser.add_argument("--agent-url", default="", help="an agent bench server already running; else one is started")
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
        rows = run_agent(models[0], options.agent_url, max(1, options.repeat))
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
        run_suite(config, results, max(1, options.repeat), options.fresh)
        row = summarise(suite, results)
        rows.append(row)
        if row["total"] and row["errors"] == row["total"]:
            # Every request failed before the model answered: the endpoint or the key is wrong, not the skill.
            print(f"Every case of {suite} failed to reach the model, stopping: {row['first_error']}", file=sys.stderr)
            break
    return finish(rows, models, options)


def run_agent(model: str, server: str, repeat: int) -> list[dict[str, Any]] | None:
    """The agent suite's row, with a server started for it unless one is given; None when none came up."""
    started = not server
    server = server or f"http://127.0.0.1:{bench.PORT}"
    if started:
        print("Starting QGIS with the plugin for the agent bench…", flush=True)
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
        run_suite(config, results, repeat, fresh=True, concurrency=1, extra_env=timeout)
        return [summarise(bench.AGENT, results)]
    finally:
        if started:
            bench.stop_server(OUT)


def finish(rows: list[dict[str, Any]], models: list[str], options: argparse.Namespace) -> int:
    """Print and keep the summary; set or check the floors when asked. 1 when a suite falls below its floor."""
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
            problems = thresholds.check(rows, models[0], thresholds.load(), require)
            verdict = "\n".join(f"- {problem}" for problem in problems) or "Every suite is at or above its floor."
            summary += f"\n### Floors\n\n{verdict}\n"
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(f"## Skill evals\n\n{summary}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
