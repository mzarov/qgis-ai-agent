from typing import Any

from ai_agent.i18n import tr

PROBE_PROMPT = "Reply with one word: ok"
REPLY_LIMIT = 160
EMPTY_REPLY = tr("Connected, but the model returned an empty answer.")


def probe(overrides: dict[str, Any]) -> tuple[bool, str]:
    from ai_agent.core.llm.transport import call_model

    try:
        turn = call_model(
            [{"role": "user", "content": PROBE_PROMPT}],
            [],
            overrides=overrides,
            timeout=60,
        )
    except Exception as error:
        return False, _shortened(str(error) or type(error).__name__)
    reply = turn.text
    if not reply.strip():
        return False, EMPTY_REPLY
    return True, tr("Model replied: {0}").format(_shortened(reply))


def _shortened(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= REPLY_LIMIT else flat[:REPLY_LIMIT] + "…"
