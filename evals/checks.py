"""The one assertion every case uses: did the model's next move match the case's `expect`?

`expect` sits in the case's vars, so a case reads as a request and its answer:

    call: set_categories                  # a tool the model called; a list means any of them
    args: {layer_name: roads, field: highway}
    loads: [osm, processing]              # skills named by its load_skill calls, at least these
    not: [run_python]                     # tools it must not call
    not_loads: [python]                   # skills it must not load
    answer: true                          # it answered in words, no tool call
    any_of: [{...}, {...}]                # any one of these expectations

Values match leniently, the way a person reads them: strings ignore case and
surrounding space, numbers compare as numbers ("500" is 500), a dict matches
when its keys do, a list against a list means "at least these", a list against
one value means "any of these", "re:<pattern>" searches, and "*" only asks
for the argument to be there.
"""

import json
import re
from typing import Any

LOAD_SKILL = "load_skill"
REGEX_PREFIX = "re:"
PRESENT = "*"
TOLERANCE = 1e-6


def expected(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Promptfoo's grading result for this case."""
    expect = (context.get("vars") or {}).get("expect") or {}
    calls = tool_calls(output)
    problem = mismatch(expect, calls)
    seen = "; ".join(f"{name}({json.dumps(args, ensure_ascii=False)})" for name, args in calls) or "no tool call"
    return {
        "pass": problem is None,
        "score": 1.0 if problem is None else 0.0,
        "reason": f"ok: {seen}" if problem is None else f"{problem}. The model did: {seen}",
    }


def mismatch(expect: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]) -> str | None:
    """None when the calls meet the expectation, else what is missing."""
    alternatives = expect.get("any_of")
    if alternatives:
        problems = [mismatch(option, calls) for option in alternatives]
        return None if any(problem is None for problem in problems) else " / ".join(str(p) for p in problems)
    names = [name for name, _ in calls]
    if expect.get("answer") and calls:
        return "expected an answer in words, not a tool call"
    forbidden = [name for name in _as_list(expect.get("not")) if name in names]
    if forbidden:
        return f"called {', '.join(forbidden)}, which this case forbids"
    loaded = [str(skill) for name, args in calls if name == LOAD_SKILL for skill in _as_list(args.get("names"))]
    wanted = [skill for skill in _as_list(expect.get("loads")) if skill not in loaded]
    if wanted:
        return f"did not load {', '.join(wanted)}"
    unwanted = [skill for skill in _as_list(expect.get("not_loads")) if skill in loaded]
    if unwanted:
        return f"loaded {', '.join(unwanted)}, which this case does not need"
    tools = _as_list(expect.get("call"))
    if tools:
        candidates = [(name, args) for name, args in calls if name in tools]
        if not candidates:
            return f"did not call {' or '.join(tools)}"
        wanted_args = expect.get("args") or {}
        if not any(matches(wanted_args, args) for _, args in candidates):
            return f"called {candidates[0][0]} without {json.dumps(wanted_args, ensure_ascii=False)}"
    return None


def tool_calls(output: Any) -> list[tuple[str, dict[str, Any]]]:
    """(name, arguments) of every tool call in a promptfoo output, whatever shape it came in."""
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except ValueError:
            return []
    if isinstance(output, dict):
        output = output.get("tool_calls") or []
    calls = []
    for item in output if isinstance(output, list) else []:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else item
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except ValueError:
                arguments = {}
        if function.get("name"):
            calls.append((str(function["name"]), arguments if isinstance(arguments, dict) else {}))
    return calls


def matches(expected_value: Any, actual: Any) -> bool:
    if isinstance(expected_value, dict):
        return isinstance(actual, dict) and all(
            key in actual and matches(value, actual[key]) for key, value in expected_value.items()
        )
    if isinstance(expected_value, list):
        if isinstance(actual, list):
            return all(any(matches(item, candidate) for candidate in actual) for item in expected_value)
        return any(matches(item, actual) for item in expected_value)
    if expected_value == PRESENT:
        return actual is not None
    if isinstance(expected_value, bool) or isinstance(actual, bool):
        return expected_value == actual
    if isinstance(expected_value, (int, float)):
        number = _number(actual)
        return number is not None and abs(number - expected_value) <= TOLERANCE * max(1.0, abs(expected_value))
    text = str(expected_value)
    if text.startswith(REGEX_PREFIX):
        return re.search(text[len(REGEX_PREFIX) :], _text(actual), re.IGNORECASE) is not None
    return text.strip().casefold() == _text(actual).strip().casefold()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
