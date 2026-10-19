from typing import Any

from ai_agent.core.llm.dialects import host_of, is_openrouter

DEEPSEEK_HOSTS = ("api.deepseek.com",)
REASONING_EFFORT = "medium"
REASONING_KEY = "reasoning_text"
DEEPSEEK_ECHO_KEY = "reasoning_content"


def is_deepseek(url: str) -> bool:
    return host_of(url) in DEEPSEEK_HOSTS


def request_options(url: str, enabled: bool) -> dict[str, Any]:
    if is_deepseek(url):
        # DeepSeek V4 thinks by default: off must be sent explicitly.
        return {"thinking": {"type": "enabled" if enabled else "disabled"}}
    if not enabled:
        return {}
    if is_openrouter(url):
        return {"reasoning": {"effort": REASONING_EFFORT}}
    return {"reasoning_effort": REASONING_EFFORT}


def wire_messages(messages: list[dict[str, Any]], url: str, enabled: bool) -> list[dict[str, Any]]:
    # DeepSeek thinking answers 400 with tools unless every earlier assistant turn has reasoning_content.
    echo = enabled and is_deepseek(url)
    wired = []
    for message in messages:
        clean = {key: value for key, value in message.items() if key != REASONING_KEY}
        if echo and clean.get("role") == "assistant":
            clean[DEEPSEEK_ECHO_KEY] = str(message.get(REASONING_KEY) or "")
        wired.append(clean)
    return wired
