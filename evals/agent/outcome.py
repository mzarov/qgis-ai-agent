"""The agent bench's assertion: did the task leave the project the way the request asked?

The server answers with what the run did and a snapshot of the project (state.py).
A task's `expect` names the outcome, never the route:

    answer: "re:\\b5\\b"                       # the final answer
    layers: {districts: {renderer: graduatedSymbol, class_attribute: pop2020, classes: 5}}
    new_layers: [{geometry: polygon, feature_count: 9}]   # each matches some layer the run added
    files: [roads.gpkg]                         # files the run wrote into the task folder
    project: {crs: EPSG:32637}
    calls: [chart_layer]                        # tools that ran and succeeded; `not_calls` for tools that must not run
    asked: true                                 # the agent was right to stop and ask
    any_of: [{...}, {...}]                      # any one of these outcomes

Values match like the skill bench's (evals/checks.py): case-insensitive strings,
numbers as numbers, dicts by their keys, `re:` patterns, `*` for presence. A run
that stopped to ask, left a batch unapplied or timed out fails unless the task
expects it.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checks import matches  # noqa: E402

FIRST_LINES = 6


def outcome(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    result = _parsed(output)
    expect = (context.get("vars") or {}).get("expect") or {}
    problems = problems_in(result, expect)
    usage = result.get("usage") or {}
    spent = f"{result.get('seconds', 0)} s, {usage.get('requests', 0)} requests"
    calls = ", ".join(call.get("name", "?") for call in result.get("calls") or []) or "no tool"
    return {
        "pass": not problems,
        "score": 0.0 if problems else 1.0,
        "reason": ("ok" if not problems else "; ".join(problems)) + f" ({spent}; ran {calls})",
        "namedScores": {"requests": float(usage.get("requests", 0)), "seconds": float(result.get("seconds", 0))},
    }


def problems_in(result: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    alternatives = expect.get("any_of")
    if alternatives:
        base = {key: value for key, value in expect.items() if key != "any_of"}
        found = [problems_in(result, {**base, **option}) for option in alternatives]
        return [] if any(not problems for problems in found) else [" / ".join("; ".join(p) for p in found)]
    if result.get("error"):
        lines = str(result["error"]).strip().splitlines()
        return ["the server failed: " + " | ".join(lines[-FIRST_LINES:])]
    problems = []
    if not (result.get("usage") or {}).get("requests"):
        # Nothing reached the model: the server's address, model or key is wrong, not the agent.
        failures = "; ".join(result.get("failures") or []) or "no failure was reported"
        return [f"no model request succeeded ({_short(failures)}); check EVAL_API_URL, EVAL_MODEL and EVAL_API_KEY"]
    if result.get("timed_out"):
        problems.append("the run did not finish in time")
    if bool(result.get("asked")) != bool(expect.get("asked", False)):
        problems.append("the agent stopped to ask" if result.get("asked") else "the agent did not ask")
    if result.get("pending"):
        problems.append("a prepared batch was left unapplied")
    state = result.get("state") or {}
    if "answer" in expect and not matches(expect["answer"], result.get("answer") or ""):
        problems.append(f"the answer does not match {expect['answer']!r}: {_short(result.get('answer'))}")
    layers = state.get("layers") or {}
    for name, wanted in (expect.get("layers") or {}).items():
        actual = layers.get(name)
        if actual is None:
            problems.append(f"no layer {name!r} is left")
        elif not matches(wanted, actual):
            problems.append(f"{name} is {_relevant(actual, wanted)}, expected {json.dumps(wanted, ensure_ascii=False)}")
    added = state.get("new_layers") or []
    for wanted in expect.get("new_layers") or []:
        if not any(matches(wanted, layer) for layer in added):
            seen = [_relevant(layer, wanted) for layer in added] or "none"
            problems.append(f"no new layer like {json.dumps(wanted, ensure_ascii=False)}; new layers: {seen}")
    files = state.get("files") or []
    for wanted in expect.get("files") or []:
        if not any(matches(wanted, name) for name in files):
            problems.append(f"no file {wanted!r} was written; files: {files or 'none'}")
    if "project" in expect and not matches(expect["project"], state.get("project") or {}):
        problems.append(f"the project is {_relevant(state.get('project') or {}, expect['project'])}")
    calls = result.get("calls") or []
    names = [call.get("name") for call in calls]
    # A tool that ran and failed did not do the task: a chart that never drew is no chart.
    succeeded = [call.get("name") for call in calls if call.get("ok")]
    for name in expect.get("calls") or []:
        if name not in succeeded:
            problems.append(f"{name} failed" if name in names else f"{name} never ran")
    problems.extend(f"{name} ran, which this task forbids" for name in expect.get("not_calls") or [] if name in names)
    return problems


def _parsed(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return {"error": f"the provider returned no JSON: {_short(output)}"}
    return parsed if isinstance(parsed, dict) else {"error": "the provider returned no object"}


def _relevant(actual: dict[str, Any], wanted: dict[str, Any]) -> str:
    """The actual values of the keys a check asked about, so a failure reads as a comparison."""
    shown = {key: actual.get(key) for key in wanted} if isinstance(wanted, dict) else actual
    if isinstance(actual, dict) and "name" in actual:
        shown = {"name": actual["name"], **shown}
    return json.dumps(shown, ensure_ascii=False)


def _short(text: Any, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
