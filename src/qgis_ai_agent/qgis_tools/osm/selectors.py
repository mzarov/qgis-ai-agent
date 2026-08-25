from typing import Any

ELEMENT_WORDS = ("node", "way", "relation", "rel", "nwr", "nw", "wr")
FORBIDDEN = (";", "[out:", "out ", "->", "/*", "//")
MAX_SELECTORS = 12
MAX_LENGTH = 400
SHAPE_HINT = (
    'Селектор пишется как node["amenity"="cafe"] или way["highway"!="track"]: '
    "тип элемента, затем условия в квадратных скобках. Без точки с запятой — "
    "территорию и вывод плагин допишет сам."
)


def normalize(raw: Any) -> list[str]:
    items = _as_list(raw)
    if not items:
        raise ValueError(f"Список selectors пуст. {SHAPE_HINT}")
    if len(items) > MAX_SELECTORS:
        raise ValueError(
            f"Селекторов {len(items)}, это больше предела в {MAX_SELECTORS}. "
            "Объедините условия регулярным выражением вида "
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
    raise ValueError(f"selectors передаётся списком строк. {SHAPE_HINT}")


def _checked(item: Any, index: int) -> str:
    text = str(item or "").strip()
    if not text:
        raise ValueError(f"Селектор {index} пустой. {SHAPE_HINT}")
    if len(text) > MAX_LENGTH:
        raise ValueError(f"Селектор {index} длиннее {MAX_LENGTH} символов — упростите его.")
    _check_forbidden(text, index)
    _check_head(text, index)
    _check_brackets(text, index)
    return text


def _check_forbidden(text: str, index: int) -> None:
    for token in FORBIDDEN:
        if token in text:
            raise ValueError(
                f"В селекторе {index} есть «{token.strip()}» — так нельзя: "
                f"один селектор описывает один набор объектов. {SHAPE_HINT}"
            )


def _check_head(text: str, index: int) -> None:
    head = text.split("[")[0].strip()
    if head not in ELEMENT_WORDS:
        raise ValueError(
            f"Селектор {index} начинается с «{head or text[:20]}», а должен — "
            f"с типа элемента: {', '.join(ELEMENT_WORDS[:3])}. {SHAPE_HINT}"
        )


def _check_brackets(text: str, index: int) -> None:
    if text.count("[") != text.count("]"):
        raise ValueError(f"В селекторе {index} не сходятся квадратные скобки.")
    if "[" not in text:
        raise ValueError(
            f"В селекторе {index} нет ни одного условия в скобках — такой запрос "
            "вытянул бы всё подряд. Добавьте хотя бы один тег."
        )
