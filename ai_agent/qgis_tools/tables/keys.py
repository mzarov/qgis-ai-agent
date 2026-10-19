# A cached QGIS join compares QVariant::toString() texts: 1 matches "1" and 1.0, not "001".

import math
from collections.abc import Iterable
from typing import Any

from ai_agent.qgis_tools.tables.delimited import BOOLEAN, DOUBLE, INTEGER, boolean_pair, parse_number

SHOWN_KEYS = 5
EXACT_FLOAT_LIMIT = 1e15


def key_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if value.isNull():
            return None
    except AttributeError:
        pass
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer() and abs(value) < EXACT_FLOAT_LIMIT:
            return str(int(value))
        return repr(value)
    return str(value)


def file_key_texts(values: Iterable[str], kind: str, decimal_comma: bool = False) -> set[str]:
    texts: set[str] = set()
    present = [raw for raw in values if raw.strip()]
    pair = boolean_pair([raw.strip() for raw in present]) if kind == BOOLEAN else None
    for raw in present:
        value = raw.strip()
        if pair is not None:
            texts.add("true" if value.lower() == pair[0] else "false")
        elif kind == INTEGER:
            texts.add(str(int(value)))
        elif kind == DOUBLE:
            number = parse_number(value, decimal_comma)
            text = key_text(number) if number is not None else value
            texts.add(text if text is not None else value)
        else:
            texts.add(raw)
    return texts


def match_report(target_keys: set[str], table_keys: set[str]) -> dict[str, Any]:
    matched = target_keys & table_keys
    missing = sorted(target_keys - table_keys)
    report: dict[str, Any] = {
        "target_keys": len(target_keys),
        "matched_keys": len(matched),
        "unmatched_keys": len(missing),
        "unused_table_keys": len(table_keys - target_keys),
    }
    if missing:
        report["unmatched_samples"] = missing[:SHOWN_KEYS]
    if target_keys and table_keys and not matched:
        report["table_samples"] = sorted(table_keys)[:SHOWN_KEYS]
        report["hint"] = mismatch_hint(target_keys, table_keys)
    return report


def mismatch_hint(target_keys: set[str], table_keys: set[str]) -> str:
    if _overlap(target_keys, table_keys, str.strip):
        return 'The keys differ only by surrounding spaces; trim them with a virtual field (trim("field")).'
    if _overlap(target_keys, table_keys, _without_zeros):
        return (
            "The keys differ only by leading zeros (e.g. '007' vs '7'): one side is text, the other a number. "
            'Join on a virtual field that converts one side — to_int("code") or lpad(to_string("code"), 3, \'0\').'
        )
    if _overlap(target_keys, table_keys, str.casefold):
        return 'The keys differ only by letter case; join on a virtual field with upper("field") on both sides.'
    return "No key value is shared; check that the two fields hold the same kind of code."


def _overlap(left: set[str], right: set[str], normal: Any) -> bool:
    return bool({normal(value) for value in left} & {normal(value) for value in right})


def _without_zeros(value: str) -> str:
    stripped = value.strip()
    return stripped.lstrip("0") or ("0" if stripped else "")
