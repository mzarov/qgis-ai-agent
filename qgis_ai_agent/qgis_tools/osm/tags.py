import re
from typing import Any

from qgis.core import QgsField
from qgis.PyQt.QtCore import QVariant

TAGS_FIELD = "other_tags"
KEY_PATTERN = re.compile(r'"([^"]+)"=>')
MAX_PROMOTED = 40
SCAN_LIMIT = 4000
EXPRESSION = "map_get(hstore_to_map(\"{field}\"), '{tag}')"
UNSAFE_CHARS = ("'", '"', "\\", "(", ")")
MAX_TAG_CHARS = 63


def promote_tags(layer: Any) -> list[str]:
    try:
        taken = set(layer.fields().names())
    except Exception:
        return []
    if TAGS_FIELD not in taken:
        return []
    promoted: list[str] = []
    for tag in _tag_names(layer):
        if len(promoted) >= MAX_PROMOTED:
            break
        if tag in taken or not _usable(tag):
            continue
        if _add_one(layer, tag):
            taken.add(tag)
            promoted.append(tag)
    return promoted


def _add_one(layer: Any, tag: str) -> bool:
    try:
        layer.addExpressionField(EXPRESSION.format(field=TAGS_FIELD, tag=tag), QgsField(tag, QVariant.String))
    except Exception:
        return False
    return True


def _usable(tag: str) -> bool:
    if not tag or len(tag) > MAX_TAG_CHARS:
        return False
    return not any(char in tag for char in UNSAFE_CHARS)


def _tag_names(layer: Any) -> list[str]:
    counts: dict[str, int] = {}
    try:
        for seen, feature in enumerate(layer.getFeatures()):
            if seen >= SCAN_LIMIT:
                break
            for key in KEY_PATTERN.findall(str(feature[TAGS_FIELD] or "")):
                counts[key] = counts.get(key, 0) + 1
    except Exception:
        return []
    return sorted(counts, key=lambda tag: (-counts[tag], tag))
