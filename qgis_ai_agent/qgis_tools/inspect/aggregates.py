import statistics
from typing import Any

NUMERIC_AGGREGATES = ("sum", "mean", "median", "min", "max", "stdev")
AGGREGATE_FUNCTIONS = ("count", "count_distinct", "concatenate") + NUMERIC_AGGREGATES
CONCAT_SEPARATOR = ", "
MAX_CONCAT_ITEMS = 50
ROUND_DIGITS = 4


def compute(function: str, values: list[Any], matched: int) -> Any:
    name = (function or "").strip().lower()
    if name not in AGGREGATE_FUNCTIONS:
        raise ValueError(
            f"Неизвестная агрегатная функция: «{function}». "
            f"Доступные: {', '.join(AGGREGATE_FUNCTIONS)}."
        )
    if name == "count":
        return matched
    filled = [value for value in values if value is not None]
    if name == "count_distinct":
        return len({_hashable(value) for value in filled})
    if name == "concatenate":
        return _concatenate(filled)
    return _numeric(name, filled)


def _concatenate(values: list[Any]) -> str:
    shown = [str(value) for value in values[:MAX_CONCAT_ITEMS]]
    text = CONCAT_SEPARATOR.join(shown)
    if len(values) > MAX_CONCAT_ITEMS:
        return text + f"… (всего {len(values)})"
    return text


def _numeric(name: str, values: list[Any]) -> Any:
    numbers = _as_numbers(name, values)
    if not numbers:
        return None
    if name == "sum":
        return _round(sum(numbers))
    if name == "mean":
        return _round(statistics.fmean(numbers))
    if name == "median":
        return _round(statistics.median(numbers))
    if name == "min":
        return _round(min(numbers))
    if name == "max":
        return _round(max(numbers))
    if len(numbers) < 2:
        return None
    return _round(statistics.stdev(numbers))


def _as_numbers(name: str, values: list[Any]) -> list[float]:
    numbers = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"Функция «{name}» работает только с числами, а встретилось "
                f"значение {value!r}. Проверьте поле или выражение."
            )
        numbers.append(float(value))
    return numbers


def _round(value: float) -> float:
    return round(float(value), ROUND_DIGITS)


def _hashable(value: Any) -> Any:
    try:
        hash(value)
    except TypeError:
        return str(value)
    return value
