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

    python3 evals/run.py                      # every suite
    python3 evals/run.py --suites routing,style --repeat 3
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


def run_suite(config: Path, results: Path, repeat: int) -> None:
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
        str(MAX_CONCURRENCY),
        "--repeat",
        str(repeat),
        "--no-progress-bar",
    ]
    environment = {
        **os.environ,
        # The same Python builds the prompts and runs the checks; nothing about the run leaves the machine.
        "PROMPTFOO_PYTHON": sys.executable,
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "PROMPTFOO_DISABLE_SHARING": "1",
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
    errors = [str(row.get("error")) for row in rows if row.get("error") and not row.get("success")]
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


def report(rows: list[dict[str, Any]]) -> str:
    lines = ["| suite | passed | tokens | mean latency |", "| --- | --- | --- | --- |"]
    for row in rows:
        lines.append(
            f"| {row['suite']} | {row['passed']}/{row['total']} | {row['tokens']:,} | {row['latency']:.1f} s |"
        )
    passed = sum(row["passed"] for row in rows)
    total = sum(row["total"] for row in rows)
    lines.append(f"| **all** | **{passed}/{total}** | {sum(row['tokens'] for row in rows):,} | |")
    for row in rows:
        if row["failures"]:
            lines.append(f"\n### {row['suite']}: failed\n")
            lines.extend(f"- {failure}" for failure in row["failures"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the skill evals through promptfoo.")
    parser.add_argument("--suites", default="", help="comma-separated suites (default: all)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case, for a pass rate")
    parser.add_argument("--configs-only", action="store_true", help="write the configs and stop")
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
        run_suite(config, results, max(1, options.repeat))
        row = summarise(suite, results)
        rows.append(row)
        if row["total"] and row["errors"] == row["total"]:
            # Every request failed before the model answered: the endpoint or the key is wrong, not the skill.
            print(f"Every case of {suite} failed to reach the model, stopping: {row['first_error']}", file=sys.stderr)
            break
    if rows:
        summary = report(rows)
        (OUT / "summary.md").write_text(summary, encoding="utf-8")
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
