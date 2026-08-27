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
    authority = (url or "").split("//")[-1].split("/")[0].strip().lower()
    if authority.startswith("["):
        return authority[1:].split("]")[0]
    return authority.split(":")[0]


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
