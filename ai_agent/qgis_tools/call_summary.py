"""A call label that knows which of its spans are the call's own values.

The feed shows a call the way Claude Code does, "Ran python3…": the wording
muted, the target bright. A tool's `summarize_call` writes plain text, so the
registry marks the spans that repeat the call's arguments verbatim. The object
is still a `str`, so every caller that only wants the text is unaffected.
"""

from string import Formatter
from typing import Any

MIN_TEXT_VALUE = 2
MAX_DEPTH = 3

Part = tuple[str, bool]


class CallSummary(str):
    parts: tuple[Part, ...]

    def __new__(cls, parts: list[Part]) -> "CallSummary":
        merged = _merge(parts)
        summary = super().__new__(cls, "".join(text for text, _ in merged))
        summary.parts = tuple(merged)
        return summary

    @classmethod
    def of(cls, template: str, *values: Any) -> "CallSummary":
        """Fill `{0}`-style placeholders, marking each value; a summary keeps its own marks."""
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
        """Mark every argument value that appears in `text` as a whole word."""
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
    # "name" must not light up inside "renamed"; a value that itself starts or
    # ends with punctuation has its own boundary there.
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
