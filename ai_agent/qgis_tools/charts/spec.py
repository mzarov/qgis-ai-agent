"""Chart and table specifications: plain JSON the feed draws, checked before anything is shown.

The limits keep a chart readable: categorical colours come in a fixed order of
eight, so more categories fold into "Other"; scatter separates at most three.
"""

import math
from typing import Any

from ai_agent.qgis_tools.base import RESULT_VISUAL_KEY

KINDS = ("bar", "line", "pie", "scatter", "histogram")
MAX_SERIES = 4
MAX_SCATTER_SERIES = 3
MAX_CATEGORIES = 40
MAX_PIE_SLICES = 8
MAX_POINTS = 500
MAX_TEXT = 80
MAX_TABLE_ROWS = 50
MAX_TABLE_COLUMNS = 10
MAX_CELL = 120
OTHER = "Other"


def chart(
    kind: str,
    title: str,
    labels: list[str],
    series: list[dict[str, Any]],
    x_label: str = "",
    y_label: str = "",
    unit: str = "",
) -> dict[str, Any]:
    """A validated chart spec; raises ValueError with a fix the model can apply."""
    kind = str(kind or "bar").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}.")
    if not series:
        raise ValueError("series is empty: give at least one series of values.")
    limit = MAX_SCATTER_SERIES if kind == "scatter" else MAX_SERIES
    if len(series) > limit:
        raise ValueError(f"{len(series)} series is too many to tell apart; show at most {limit}, or split the chart.")
    cleaned = [_series(item, kind) for item in series]
    labels = [_text(label) for label in labels]
    if kind != "scatter":
        if not labels:
            raise ValueError("labels is empty: name the categories or x values.")
        if len(labels) > MAX_CATEGORIES:
            raise ValueError(f"{len(labels)} categories will not fit; keep the top {MAX_CATEGORIES} or group them.")
        for item in cleaned:
            if len(item["values"]) != len(labels):
                raise ValueError(f"Series '{item['name']}' has {len(item['values'])} values for {len(labels)} labels.")
    if kind == "pie":
        if len(cleaned) != 1:
            raise ValueError("A pie shows one series.")
        if any(value is not None and value < 0 for value in cleaned[0]["values"]):
            raise ValueError("A pie cannot show negative values; use a bar chart.")
        labels, cleaned[0]["values"] = fold_other(labels, cleaned[0]["values"], MAX_PIE_SLICES)
    return {
        "type": "chart",
        "kind": kind,
        "title": _text(title),
        "labels": labels,
        "series": cleaned,
        "x_label": _text(x_label),
        "y_label": _text(y_label),
        "unit": _text(unit),
    }


def table(title: str, columns: list[str], rows: list[list[Any]], total: int) -> dict[str, Any]:
    columns = [_text(column) for column in columns[:MAX_TABLE_COLUMNS]]
    shown = [[_cell(value) for value in row[: len(columns)]] for row in rows[:MAX_TABLE_ROWS]]
    return {"type": "table", "title": _text(title), "columns": columns, "rows": shown, "total": int(total)}


def fold_other(labels: list[str], values: list[float | None], keep: int) -> tuple[list[str], list[float | None]]:
    """The largest `keep - 1` categories and one "Other" summing the rest, when there are more than `keep`."""
    if len(labels) <= keep:
        return labels, values
    order = sorted(range(len(values)), key=lambda index: -(values[index] or 0))
    kept = sorted(order[: keep - 1])
    rest = sum(values[index] or 0 for index in order[keep - 1 :])
    return [labels[index] for index in kept] + [OTHER], [values[index] for index in kept] + [rest]


def attach(result: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    """The tool result with the spec riding along for the feed; the executor strips it before the model."""
    return {**result, RESULT_VISUAL_KEY: visual}


def _series(item: Any, kind: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError('Each series is an object: {"name": "2020", "values": [1, 2, 3]}.')
    name = _text(item.get("name") or "")
    values = _numbers(item.get("values"), name)
    cleaned: dict[str, Any] = {"name": name, "values": values}
    if kind == "scatter":
        xs = _numbers(item.get("x"), name)
        if len(xs) != len(values):
            raise ValueError(f"Scatter series '{name}' needs as many x as values.")
        cleaned["x"] = xs
    if len(values) > MAX_POINTS:
        raise ValueError(f"Series '{name}' has {len(values)} points; at most {MAX_POINTS} are drawn.")
    return cleaned


def _numbers(raw: Any, name: str) -> list[float | None]:
    if not isinstance(raw, list):
        raise ValueError(f"Series '{name}' needs values as a list of numbers.")
    numbers: list[float | None] = []
    for value in raw:
        if value is None:
            numbers.append(None)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Series '{name}' holds '{value}', which is not a number.") from None
        numbers.append(number if math.isfinite(number) else None)
    return numbers


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_TEXT]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.6g}" if abs(value) < 1e15 else str(value)
    return " ".join(str(value).split())[:MAX_CELL]
