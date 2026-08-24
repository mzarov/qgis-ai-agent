def build_clarification_questions(steps: list[dict]) -> list[dict]:
    """Формирует короткие уточнения только при реальной нехватке данных."""
    questions: list[dict] = []
    has_scalebar = any((step.get("tool") or "") == "add_scale_bar" for step in steps)
    for index, step in enumerate(steps):
        tool = (step.get("tool") or "").strip()
        params = step.get("params") or {}
        if tool == "add_label":
            text = (params.get("text") or "").strip()
            if not text:
                questions.append(
                    {
                        "id": "missing_label_text",
                        "step_index": index,
                        "field": "text",
                        "question": "Какой точный текст нужно добавить на макет?",
                    }
                )
        if tool == "add_scale_bar":
            units = (params.get("units") or "").strip().lower()
            if units and units not in ("m", "km", "meters", "kilometers"):
                questions.append(
                    {
                        "id": "scalebar_units_check",
                        "step_index": index,
                        "field": "units",
                        "question": "Подтвердите единицы масштабной линейки (m/km), чтобы подписи были читаемыми.",
                    }
                )
    if has_scalebar and len(questions) > 1:
        return questions[:1]
    return questions


def apply_clarification_answer(data: dict, answer: str) -> dict:
    """Применяет ответ пользователя к первому ожидающему уточнению."""
    questions = data.get("clarification_questions") or []
    steps = data.get("steps") or []
    if not questions or not steps:
        return data

    question = questions[0]
    step_index = int(question.get("step_index", 0))
    field = (question.get("field") or "").strip()
    if step_index < 0 or step_index >= len(steps) or not field:
        data["clarification_questions"] = questions[1:]
        return data

    params = steps[step_index].setdefault("params", {})
    raw_answer = (answer or "").strip()
    if field in ("x", "y", "font_size", "units_per_segment", "segment_count"):
        try:
            params[field] = float(raw_answer.replace(",", "."))
        except Exception:
            params[field] = raw_answer
    else:
        params[field] = raw_answer
    data["steps"] = steps
    data["clarification_questions"] = questions[1:]
    return data
