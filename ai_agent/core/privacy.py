from ai_agent.core.llm.dialects import safe_endpoint_label


def endpoint_label(url: str) -> str:
    return safe_endpoint_label(url)
