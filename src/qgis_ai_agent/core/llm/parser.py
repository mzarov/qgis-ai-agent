import json
import re

# Ключи управляющего объекта JSON-протокола — по ним выбирается лучший кандидат.
PRIORITY_KEYS = ("tool_calls", "text", "done")


def parse_model_json(reply: str) -> dict:
    """Извлекает JSON из raw-ответа модели."""
    raw = (reply or "").strip()
    if "```" in raw:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _parse_first_valid_object(raw)


def _parse_first_valid_object(raw: str) -> dict:
    """
    Устойчивый разбор: LLM иногда возвращает несколько JSON подряд
    или добавляет текст до/после объекта.
    """
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict]] = []
    for idx, ch in enumerate(raw):
        if ch not in "{[":
            continue
        try:
            parsed, end_idx = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates.append((idx + end_idx, parsed))

    if not candidates:
        raise json.JSONDecodeError("No valid JSON object found", raw, 0)

    # Предпочитаем наиболее «полный» control-object, если их несколько.
    ranked = sorted(
        candidates,
        key=lambda item: (
            sum(1 for key in PRIORITY_KEYS if key in item[1]),
            item[0],
        ),
        reverse=True,
    )
    return ranked[0][1]


def parse_tool_arguments(raw_arguments) -> dict:
    """
    Разбирает поле arguments из tool_call.
    Модели отдают его строкой JSON, но встречается и готовый объект.
    """
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    text = (raw_arguments or "").strip() if isinstance(raw_arguments, str) else ""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = _parse_first_valid_object(text)
        except json.JSONDecodeError:
            return {}
    return dict(parsed) if isinstance(parsed, dict) else {}
