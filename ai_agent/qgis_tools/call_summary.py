from string import Formatter
from typing import Any

MIN_TEXT_VALUE = 2
MAX_DEPTH = 3

Part = tuple[str, bool]


class CallSummary(str):
    parts: tuple[Part, ...]
    skill: str = ""

    def __new__(cls, parts: list[Part]) -> "CallSummary":
        merged = _merge(parts)
        summary = super().__new__(cls, "".join(text for text, _ in merged))
        summary.parts = tuple(merged)
        return summary

    @classmethod
    def of(cls, template: str, *values: Any) -> "CallSummary":
        parts: list[Part] = []
        for literal, field, _spec, _conversion in Formatter().parse(template):
            parts.append((literal, False))
            if field is None:
                continue
            value = values[int(field or 0)]
            parts.extend(value.parts if isinstance(value, CallSummary) else [(str(value), True)])
        return cls(parts)

    @classmethod
    def marking(cls, text: str, params: dict[str, Any]) -> "CallSummary":
        spans: list[tuple[int, int]] = []
        for value in sorted(set(_values(params)), key=len, reverse=True):
            start = text.find(value)
            while start >= 0:
                end = start + len(value)
                if _bounded(text, start, end) and not any(start < b and a < end for a, b in spans):
                    spans.append((start, end))
                start = text.find(value, end)
        parts: list[Part] = []
        cursor = 0
        for start, end in sorted(spans):
            parts.extend([(text[cursor:start], False), (text[start:end], True)])
            cursor = end
        parts.append((text[cursor:], False))
        return cls(parts)


def _values(params: Any, depth: int = 0) -> list[str]:
    if depth > MAX_DEPTH:
        return []
    if isinstance(params, dict):
        return [found for value in params.values() for found in _values(value, depth + 1)]
    if isinstance(params, (list, tuple)):
        return [found for value in params for found in _values(value, depth + 1)]
    if isinstance(params, bool):
        return []
    if isinstance(params, (int, float)):
        return [str(params)]
    if isinstance(params, str):
        value = params.strip()
        return [value] if len(value) >= MIN_TEXT_VALUE else []
    return []


def _bounded(text: str, start: int, end: int) -> bool:
    before = start == 0 or not (text[start - 1].isalnum() and text[start].isalnum())
    after = end == len(text) or not (text[end].isalnum() and text[end - 1].isalnum())
    return before and after


def _merge(parts: list[Part]) -> list[Part]:
    merged: list[Part] = []
    for text, marked in parts:
        if not text:
            continue
        if merged and merged[-1][1] == marked:
            merged[-1] = (merged[-1][0] + text, marked)
        else:
            merged.append((text, marked))
    return merged
