from typing import Any

ELEMENT_WORDS = ("node", "way", "relation", "rel", "nwr", "nw", "wr")
FORBIDDEN = (";", "[out:", "out ", "->", "/*", "//")
MAX_SELECTORS = 12
MAX_LENGTH = 400
SHAPE_HINT = (
    'A selector is written as node["amenity"="cafe"] or way["highway"!="track"]: '
    "element type, then conditions in square brackets. No semicolon — "
    "the plugin appends the territory and the output statement itself."
)


def normalize(raw: Any) -> list[str]:
    items = _as_list(raw)
    if not items:
        raise ValueError(f"The selectors list is empty. {SHAPE_HINT}")
    if len(items) > MAX_SELECTORS:
        raise ValueError(
            f"There are {len(items)} selectors, which is over the limit of {MAX_SELECTORS}. "
            "Merge the conditions into a regular expression such as "
            '["amenity"~"cafe|restaurant"].'
        )
    return [_checked(item, index) for index, item in enumerate(items, 1)]


def _as_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return list(raw)
    raise ValueError(f"selectors is passed as a list of strings. {SHAPE_HINT}")


def _checked(item: Any, index: int) -> str:
    text = str(item or "").strip()
    if not text:
        raise ValueError(f"Selector {index} is empty. {SHAPE_HINT}")
    if len(text) > MAX_LENGTH:
        raise ValueError(f"Selector {index} is longer than {MAX_LENGTH} characters — simplify it.")
    _check_forbidden(text, index)
    _check_head(text, index)
    _check_brackets(text, index)
    return text


def _check_forbidden(text: str, index: int) -> None:
    for token in FORBIDDEN:
        if token in text:
            raise ValueError(
                f"Selector {index} contains '{token.strip()}', which is not allowed: "
                f"one selector describes one set of objects. {SHAPE_HINT}"
            )


def _check_head(text: str, index: int) -> None:
    head = text.split("[")[0].strip()
    if head not in ELEMENT_WORDS:
        raise ValueError(
            f"Selector {index} starts with '{head or text[:20]}', but it must start "
            f"with an element type: {', '.join(ELEMENT_WORDS[:3])}. {SHAPE_HINT}"
        )


def _check_brackets(text: str, index: int) -> None:
    if text.count("[") != text.count("]"):
        raise ValueError(f"The square brackets in selector {index} do not match up.")
    if "[" not in text:
        raise ValueError(
            f"Selector {index} has no bracketed condition at all — such a query "
            "would pull in everything. Add at least one tag."
        )
