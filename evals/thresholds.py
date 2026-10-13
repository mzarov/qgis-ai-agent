"""Pass-rate floors per suite: what CI holds a model to, so noise passes and a regression fails.

A model's answers vary from run to run, so the bench cannot demand every case.
Each suite gets a floor measured on one model: the pass rate of a baseline run
(best with --repeat 3 --fresh) less MARGIN, rounded down to STEP. The floors
apply only to the model they were measured on; another model just reports.
"""

import json
import math
from pathlib import Path
from typing import Any

PATH = Path(__file__).with_name("thresholds.json")
MARGIN = 0.1
STEP = 0.05
EPSILON = 1e-9


def load(path: Path = PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"model": "", "margin": MARGIN, "suites": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def rate(row: dict[str, Any]) -> float | None:
    """The share of graded cases that passed; None when no case reached the model."""
    graded = row["total"] - row["errors"]
    return row["passed"] / graded if graded > 0 else None


def floor_for(measured: float, margin: float = MARGIN) -> float:
    return round(max(0.0, math.floor((measured - margin) / STEP + EPSILON) * STEP), 2)


def save(rows: list[dict[str, Any]], model: str, path: Path = PATH) -> dict[str, Any]:
    """Floors from this run's suites; suites it did not run keep theirs when the model is the same."""
    current = load(path)
    suites = dict(current.get("suites") or {}) if current.get("model") == model else {}
    for row in rows:
        measured = rate(row)
        if measured is not None:
            suites[row["suite"]] = floor_for(measured)
    data = {"model": model, "margin": MARGIN, "suites": dict(sorted(suites.items()))}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def check(rows: list[dict[str, Any]], model: str, data: dict[str, Any], require: bool = False) -> list[str]:
    """What falls short: a suite below its floor, or, with `require`, a suite or model without one."""
    if data.get("model") != model:
        return [f"no floors were measured on {model}; run with --save-thresholds first"] if require else []
    floors = data.get("suites") or {}
    problems = []
    for row in rows:
        floor = floors.get(row["suite"])
        if floor is None:
            if require:
                problems.append(f"{row['suite']}: no floor yet")
            continue
        measured = rate(row)
        if measured is None:
            problems.append(f"{row['suite']}: no case reached the model")
        elif measured + EPSILON < floor:
            problems.append(f"{row['suite']}: {measured:.0%} passed, below its floor of {floor:.0%}")
    return problems
