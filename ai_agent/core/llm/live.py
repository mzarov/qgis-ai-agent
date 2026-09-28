from typing import Any

LIVE_KEY = "live_state"
LIVE_SEPARATOR = "\n\n"


def live_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text, LIVE_KEY: True}


def split_live(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    if messages and messages[-1].get(LIVE_KEY):
        return messages[:-1], str(messages[-1].get("content") or "")
    return messages, ""


def fold_live(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the per-turn state message into the last real message.

    The state is kept apart so a prompt-caching provider can end the cached
    prefix before it. Endpoints without that distinction get it appended to
    the last message, because several chat templates reject two user turns in
    a row or a user turn right after a tool result.
    """
    rest, live = split_live(messages)
    if not live:
        return rest
    if not rest or rest[-1].get("role") in ("system", "assistant"):
        return [*rest, {"role": "user", "content": live}]
    last = dict(rest[-1])
    content = last.get("content")
    if isinstance(content, list):
        last["content"] = [*content, {"type": "text", "text": live}]
    else:
        last["content"] = f"{content or ''}{LIVE_SEPARATOR}{live}" if content else live
    return [*rest[:-1], last]
