import json
import re


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
    priority_keys = ("next_stage", "steps", "can_do", "preface", "message")
    ranked = sorted(
        candidates,
        key=lambda item: (
            sum(1 for key in priority_keys if key in item[1]),
            item[0],
        ),
        reverse=True,
    )
    return ranked[0][1]
