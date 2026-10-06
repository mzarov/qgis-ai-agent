"""Axis arithmetic for the feed's charts: round ticks, compact numbers, which bar layout fits."""

import math

TICK_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)
TARGET_TICKS = 4
SHORT_LABEL = 6
MAX_VERTICAL_BARS = 12


def nice_ticks(low: float, high: float, target: int = TARGET_TICKS) -> list[float]:
    """Round tick values covering [low, high], zero included when the data reaches it."""
    if low > high:
        low, high = high, low
    if low == high:
        high = low + (abs(low) or 1.0)
    raw = (high - low) / max(1, target)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(step * magnitude for step in TICK_STEPS if step * magnitude >= raw)
    start = math.floor(low / step) * step
    ticks = []
    value = start
    while value <= high + step * 1e-9:
        ticks.append(round(value, 12))
        value += step
    if ticks[-1] < high:
        ticks.append(round(ticks[-1] + step, 12))
    return ticks


def compact(value: float) -> str:
    """1 234 567 → 1.2M; small and fractional values keep up to three significant digits."""
    magnitude = abs(value)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if magnitude >= limit:
            return f"{value / limit:.3g}{suffix}"
    if magnitude == 0 or magnitude >= 1:
        return f"{value:.4g}"
    return f"{value:.3g}"


def horizontal_bars(labels: list[str], series_count: int) -> bool:
    """Long or many category names read better as rows than squeezed under columns."""
    if len(labels) * series_count > MAX_VERTICAL_BARS:
        return True
    return any(len(label) > SHORT_LABEL for label in labels)


def value_range(series: list[list[float | None]], stacked_from_zero: bool = True) -> tuple[float, float]:
    numbers = [value for values in series for value in values if value is not None]
    if not numbers:
        return 0.0, 1.0
    low, high = min(numbers), max(numbers)
    if stacked_from_zero:
        low, high = min(low, 0.0), max(high, 0.0)
    return low, high


def thinned(count: int, room: float, width: float) -> int:
    """Show every n-th axis label so labels of `width` pixels fit into `room`."""
    if count <= 0 or width <= 0:
        return 1
    fitting = max(1, int(room // width))
    return max(1, math.ceil(count / fitting))
