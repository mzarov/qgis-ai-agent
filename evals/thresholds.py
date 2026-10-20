import json
import math
from pathlib import Path
from typing import Any

PATH = Path(__file__).with_name("thresholds.json")
MARGIN = 0.1
STEP = 0.05
EPSILON = 1e-9
# Unreached cases leave the rate; more of them than this could hide a drop past the margin.
MAX_UNREACHED_SHARE = 0.1


def load(path: Path = PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"model": "", "margin": MARGIN, "suites": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def rate(row: dict[str, Any]) -> float | None:
    graded = row["total"] - row["errors"]
    return row["passed"] / graded if graded > 0 else None


def floor_for(measured: float, margin: float = MARGIN) -> float:
    return round(max(0.0, math.floor((measured - margin) / STEP + EPSILON) * STEP), 2)


def save(rows: list[dict[str, Any]], model: str, path: Path = PATH) -> dict[str, Any]:
    current = load(path)
    suites = dict(current.get("suites") or {}) if current.get("model") == model else {}
    for row in rows:
        measured = rate(row)
        if measured is not None:
            suites[row["suite"]] = floor_for(measured)
    data = {"model": model, "margin": MARGIN, "suites": dict(sorted(suites.items()))}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def floors_of(model: str, data: dict[str, Any]) -> dict[str, float]:
    return dict(data.get("suites") or {}) if data.get("model") == model else {}


def unchecked(rows: list[dict[str, Any]], model: str, data: dict[str, Any]) -> list[str]:
    floors = floors_of(model, data)
    return [row["suite"] for row in rows if row["suite"] not in floors]


def check(rows: list[dict[str, Any]], model: str, data: dict[str, Any], require: bool = False) -> list[str]:
    if data.get("model") != model:
        return [f"no floors were measured on {model}; run with --save-thresholds first"] if require else []
    floors = floors_of(model, data)
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
        elif row["errors"] > MAX_UNREACHED_SHARE * row["total"] + EPSILON:
            problems.append(f"{row['suite']}: {row['errors']} of {row['total']} cases never reached the model")
        elif measured + EPSILON < floor:
            problems.append(f"{row['suite']}: {measured:.0%} passed, below its floor of {floor:.0%}")
    return problems
