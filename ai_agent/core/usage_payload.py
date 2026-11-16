import re
import sys
from typing import Any
from urllib.parse import urlsplit

from qgis.core import Qgis

from ai_agent.core.about import plugin_version
from ai_agent.core.llm.client import is_local
from ai_agent.core.llm.dialects import resolve
from ai_agent.core.settings import get_api_url, get_dialect, has_saved_model
from ai_agent.i18n import locale_code

PAYLOAD_VERSION = 3
NAME = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
MAX_NAMES = 150
MAX_COUNT = 100_000
VERSION_CHARS = 32
OS_FAMILIES = (("darwin", "macos"), ("win", "windows"), ("linux", "linux"))
DIALECTS = ("openai", "anthropic")
ACTIVE = "active"
REQUESTS = "runs"
RETRIES = "retries"
CHECKS = "checks"
SCALARS = (REQUESTS, "applies", RETRIES, CHECKS)
CONVERSATIONS = "conversations"
ANSWERED = "answered"
FAILED = "failed"
STOPPED = "stopped"
LIMIT = "limit"
SHOWN = "shown"
CANCELLED = "cancelled"
UNDONE = "undone"
AUTO = "auto"
COUNTED_MODES = ("plan", AUTO)
REQUEST_BUCKETS = ((1, "r1"), (2, "r2"), (5, "r3_5"), (10, "r6_10"), (None, "r11_plus"))
STEP_BUCKETS = ((0, "s0"), (1, "s1"), (3, "s2_3"), (7, "s4_7"), (15, "s8_15"), (None, "s16_plus"))
SECOND_BUCKETS = ((10, "t0_10"), (30, "t10_30"), (60, "t30_60"), (180, "t60_180"), (None, "t180_plus"))
TOKEN_BUCKETS = ((5_000, "k0_5"), (20_000, "k5_20"), (50_000, "k20_50"), (200_000, "k50_200"), (None, "k200_plus"))
MAPS = (
    "failures",
    "tools",
    "tool_errors",
    "skills",
    "outcomes",
    "modes",
    "plans",
    "to_apply",
    "steps",
    "durations",
    "tokens",
)
FAMILY_HOSTS = (
    ("api.openai.com", "openai"),
    ("openrouter.ai", "openrouter"),
    ("api.anthropic.com", "anthropic"),
    ("generativelanguage.googleapis.com", "gemini"),
    ("api.deepseek.com", "deepseek"),
    ("api.mistral.ai", "mistral"),
    ("api.groq.com", "groq"),
    ("api.x.ai", "xai"),
    ("api.together.xyz", "together"),
    ("api.fireworks.ai", "fireworks"),
    ("api.moonshot.ai", "moonshot"),
    ("api.moonshot.cn", "moonshot"),
    ("dashscope.aliyuncs.com", "qwen"),
    ("dashscope-intl.aliyuncs.com", "qwen"),
    ("open.bigmodel.cn", "zhipu"),
    ("llm.api.cloud.yandex.net", "yandex"),
    ("integrate.api.nvidia.com", "nvidia"),
    ("router.huggingface.co", "huggingface"),
    ("api.cerebras.ai", "cerebras"),
    ("api.perplexity.ai", "perplexity"),
    ("openai.azure.com", "azure"),
)
LOCAL_FAMILIES = ((11434, "ollama"), (1234, "lmstudio"))
OTHER_LOCAL = "other_local"
OTHER_REMOTE = "other_remote"


def add(counts: dict[str, Any], kind: str, name: str = "") -> dict[str, Any]:
    if kind == ACTIVE:
        counts[ACTIVE] = True
        return counts
    if kind in SCALARS:
        counts[kind] = min(MAX_COUNT, int(counts.get(kind, 0)) + 1)
        return counts
    key = str(name or "").strip().lower()
    group = counts.setdefault(kind, {})
    if not NAME.match(key) or (key not in group and len(group) >= MAX_NAMES):
        return counts
    group[key] = min(MAX_COUNT, int(group.get(key, 0)) + 1)
    return counts


def bucket(value: float, edges: tuple[tuple[int | None, str], ...]) -> str:
    return next(name for edge, name in edges if edge is None or value <= edge)


def payload(install: str, day: str, counts: dict[str, Any], plugin: str | None = None) -> dict[str, Any]:
    url = get_api_url()
    dialect = resolve(url, get_dialect())
    conversations = [int(number) for number in dict(counts.get(CONVERSATIONS) or {}).values()]
    session_requests: dict[str, int] = {}
    for number in conversations:
        name = bucket(number, REQUEST_BUCKETS)
        session_requests[name] = session_requests.get(name, 0) + 1
    body = {
        "v": PAYLOAD_VERSION,
        "install": install,
        "day": day,
        "plugin": version_text(plugin_version()) if plugin is None else plugin,
        "qgis": version_text(str(Qgis.version()).split("-")[0]),
        "os": os_family(sys.platform),
        "locale": re.sub(r"[^A-Za-z_-]", "", locale_code())[:16] or "en",
        "provider": "local" if url and is_local(url) else "remote",
        "family": provider_family(url),
        "dialect": dialect if dialect in DIALECTS else "openai",
        "configured": has_saved_model(),
        "sessions": len(conversations),
        "session_requests": session_requests,
    }
    for kind in SCALARS:
        body[kind] = int(counts.get(kind, 0))
    for kind in MAPS:
        body[kind] = dict(counts.get(kind) or {})
    return body


def provider_family(url: str) -> str:
    try:
        parts = urlsplit((url or "").strip())
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return OTHER_REMOTE
    if url and is_local(url):
        return next((family for number, family in LOCAL_FAMILIES if port == number), OTHER_LOCAL)
    known = (family for domain, family in FAMILY_HOSTS if host == domain or host.endswith("." + domain))
    return next(known, OTHER_REMOTE)


def os_family(platform: str) -> str:
    return next((family for prefix, family in OS_FAMILIES if platform.startswith(prefix)), "other")


def has_counts(counts: dict[str, Any]) -> bool:
    return bool(counts.get(ACTIVE) or counts.get("runs") or counts.get("applies") or counts.get("tools"))


def version_text(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._+-]", "", text)[:VERSION_CHARS] or "unknown"
