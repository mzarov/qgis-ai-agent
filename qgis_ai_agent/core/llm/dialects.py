import ipaddress
from urllib.parse import urlsplit

OPENAI = "openai"
ANTHROPIC = "anthropic"
AUTO = "auto"

DIALECTS = (AUTO, OPENAI, ANTHROPIC)
ANTHROPIC_HOSTS = ("api.anthropic.com",)
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_PATH = "/messages"
OPENAI_PATH = "/chat/completions"
OPENROUTER_HOSTS = ("openrouter.ai",)
REFERER = "https://github.com/mzarov/qgis-ai-agent"
TITLE = "QGIS AI Agent"
DEFAULT_MAX_TOKENS = 4096
LOOPBACK_HOSTS = ("localhost", "0.0.0.0")


def detect(url: str) -> str:
    host = host_of(url)
    if any(host == known or host.endswith("." + known) for known in ANTHROPIC_HOSTS):
        return ANTHROPIC
    return OPENAI


def resolve(url: str, chosen: str) -> str:
    wanted = (chosen or AUTO).strip().lower()
    if wanted in (OPENAI, ANTHROPIC):
        return wanted
    return detect(url)


def is_openrouter(url: str) -> bool:
    host = host_of(url)
    return any(host == known or host.endswith("." + known) for known in OPENROUTER_HOSTS)


def host_of(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text if "://" in text else f"//{text}")
    except ValueError:
        return ""
    return (parsed.hostname or "").lower()


def is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def safe_endpoint_label(url: str) -> str:
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return "configured endpoint"
    host = parsed.hostname or ""
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port else ""
    return f"{parsed.scheme or 'https'}://{host}{port}" if host else "configured endpoint"


def path_for(dialect: str) -> str:
    return ANTHROPIC_PATH if dialect == ANTHROPIC else OPENAI_PATH


def headers_for(dialect: str, key: str, auth_type: str, url: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if dialect == ANTHROPIC:
        headers["anthropic-version"] = ANTHROPIC_VERSION
        if key:
            headers["x-api-key"] = key
        return headers
    if key:
        headers["Authorization"] = f"{auth_type} {key}" if auth_type else f"Bearer {key}"
    if is_openrouter(url):
        headers["HTTP-Referer"] = REFERER
        headers["X-Title"] = TITLE
    return headers
