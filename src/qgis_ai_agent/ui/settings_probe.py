from typing import Any

PROBE_PROMPT = "Ответь одним словом: ок"
REPLY_LIMIT = 160
EMPTY_REPLY = "Подключение есть, но модель вернула пустой ответ."


def probe(overrides: dict[str, Any]) -> tuple[bool, str]:
    from qgis_ai_agent.core.llm.client import chat

    try:
        reply = chat([{"role": "user", "content": PROBE_PROMPT}], **overrides)
    except Exception as error:
        return False, _shortened(str(error) or type(error).__name__)
    if not reply.strip():
        return False, EMPTY_REPLY
    return True, f"Ответ модели: {_shortened(reply)}"


def _shortened(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= REPLY_LIMIT else flat[:REPLY_LIMIT] + "…"
