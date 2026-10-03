"""Asking an OpenAI-compatible endpoint to reason, in the shape its provider expects.

There is no standard parameter. The provider is picked from the host; an
unknown host gets OpenAI's `reasoning_effort`, the shape most compatible
servers copied. A server that rejects it costs one retry and is remembered —
the reasoning is in docs/core_architecture.md.
"""

from typing import Any

from ai_agent.core.llm.dialects import host_of, is_openrouter

DEEPSEEK_HOSTS = ("api.deepseek.com",)
REASONING_EFFORT = "medium"
# Internal key: the transcript hands each turn's reasoning to the transport, which
# either renames it for a provider that needs it back or strips it.
REASONING_KEY = "reasoning_text"
DEEPSEEK_ECHO_KEY = "reasoning_content"


def is_deepseek(url: str) -> bool:
    return host_of(url) in DEEPSEEK_HOSTS


def request_options(url: str, enabled: bool) -> dict[str, Any]:
    """Body fields that switch reasoning on (or, for DeepSeek, explicitly off)."""
    if is_deepseek(url):
        # DeepSeek V4 thinks by default; off must be said out loud, see wire_messages.
        return {"thinking": {"type": "enabled" if enabled else "disabled"}}
    if not enabled:
        return {}
    if is_openrouter(url):
        return {"reasoning": {"effort": REASONING_EFFORT}}
    return {"reasoning_effort": REASONING_EFFORT}


def wire_messages(messages: list[dict[str, Any]], url: str, enabled: bool) -> list[dict[str, Any]]:
    """Messages as they go on the wire: reasoning echoed only where the provider demands it.

    DeepSeek in thinking mode answers 400 to a request with tools unless every
    earlier assistant message carries its `reasoning_content`. Turns from this
    run have it; history and JSON-protocol turns get an empty string, which the
    API accepts. Every other endpoint never sees the reasoning text.
    """
    echo = enabled and is_deepseek(url)
    wired = []
    for message in messages:
        clean = {key: value for key, value in message.items() if key != REASONING_KEY}
        if echo and clean.get("role") == "assistant":
            clean[DEEPSEEK_ECHO_KEY] = str(message.get(REASONING_KEY) or "")
        wired.append(clean)
    return wired
