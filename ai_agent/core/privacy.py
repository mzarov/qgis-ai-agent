from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import safe_endpoint_label
from ai_agent.core.settings import get_allow_sensitive_data, get_api_url
from ai_agent.qgis_tools.base import BaseTool, is_sensitive_egress


def sensitive_data_allowed(url: str | None = None) -> bool:
    endpoint = (url if url is not None else get_api_url()) or ""
    return is_local(endpoint) or get_allow_sensitive_data(endpoint)


def tool_output_allowed(tool: BaseTool, url: str | None = None) -> bool:
    return not is_sensitive_egress(tool.egress) or sensitive_data_allowed(url)


def endpoint_label(url: str) -> str:
    return safe_endpoint_label(url)
