import re
from urllib.parse import urlsplit, urlunsplit

from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.client import scrub_secrets
from ai_agent.core.llm.turns import ToolCall
from ai_agent.i18n import tr
from ai_agent.qgis_tools.registry import summarize_tool_result

BUSY = tr("The service did not answer in time — it is busy. Try again in a minute or with a smaller area.")
RATE_LIMITED = tr("The service is limiting requests. Wait a minute and try again.")
OFFLINE = tr("Could not reach the service — check the internet connection or the QGIS proxy.")
DENIED = tr("The service refused access.")
SERVER_DOWN = tr("The service is having trouble right now. Try again later.")
GENERIC = tr("The step did not run — the agent sees why and can try another way.")

KINDS = (
    (BUSY, r"gateway timeout|timed out|timeout|\b504\b|operation canceled"),
    (RATE_LIMITED, r"too many requests|\b429\b|rate limit"),
    (OFFLINE, r"host \S+ not found|connection refused|network is unreachable|could not resolve|no route"),
    (DENIED, r"forbidden|\b403\b|unauthorized|\b401\b"),
    (SERVER_DOWN, r"internal server error|bad gateway|service unavailable|\b50[023]\b"),
)
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>()]+")


def failure_text(text: str) -> str:
    # Qt's network errors quote the whole address: its login and query may hold a key.
    return URL.sub(_bare_address, scrub_secrets(str(text)))


def _bare_address(match: re.Match[str]) -> str:
    try:
        parts = urlsplit(match.group(0))
    except ValueError:
        return ""
    return urlunsplit((parts.scheme, parts.netloc.rpartition("@")[2], parts.path, "", ""))


def explain_failure(error: str) -> str:
    lowered = str(error or "").lower()
    for sentence, pattern in KINDS:
        if re.search(pattern, lowered):
            return sentence
    return GENERIC


def outcome_note(call: ToolCall, result: ToolResult) -> str:
    if result.ok:
        return summarize_tool_result(call.name, call.arguments, result.payload)
    return explain_failure(result.error)
