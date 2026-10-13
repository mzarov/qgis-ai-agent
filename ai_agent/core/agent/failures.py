"""A failed call or run in words a person reads: the model keeps the exact English error, the feed shows its meaning.

Tool errors are written for the model — "Error transferring https://… server
replied: Gateway Timeout" with a recovery hint. Shown as they are, they read as
a crash dump in the middle of a Russian chat. The common network failures get a
plain sentence, anything else a generic one; the model still reads the original.
"""

import re
from dataclasses import dataclass
from typing import Any

from ai_agent.core.llm import failure_kinds as kinds
from ai_agent.i18n import tr
from ai_agent.qgis_tools.registry import summarize_tool_result

BUSY = tr("The service did not answer in time — it is busy. Try again in a minute or with a smaller area.")
RATE_LIMITED = tr("The service is limiting requests. Wait a minute and try again.")
OFFLINE = tr("Could not reach the service — check the internet connection or the QGIS proxy.")
DENIED = tr("The service refused access.")
SERVER_DOWN = tr("The service is having trouble right now. Try again later.")
GENERIC = tr("The step did not run — the agent sees why and can try another way.")

# Checked in order: a "504 Gateway Timeout" is busy, not down. Qt words a DNS failure "Host x not found".
KINDS = (
    (BUSY, r"gateway timeout|timed out|timeout|\b504\b|operation canceled"),
    (RATE_LIMITED, r"too many requests|\b429\b|rate limit"),
    (OFFLINE, r"host \S+ not found|connection refused|network is unreachable|could not resolve|no route"),
    (DENIED, r"forbidden|\b403\b|unauthorized|\b401\b"),
    (SERVER_DOWN, r"internal server error|bad gateway|service unavailable|\b50[023]\b"),
)


def explain_failure(error: str) -> str:
    """The person-facing sentence for a tool error; GENERIC when the kind is not recognised."""
    lowered = str(error or "").lower()
    for sentence, pattern in KINDS:
        if re.search(pattern, lowered):
            return sentence
    return GENERIC


def outcome_note(call: Any, result: Any) -> str:
    """The line under a finished call: what it found, or why it failed in plain words."""
    if result.ok:
        return summarize_tool_result(call.name, call.arguments, result.payload)
    return explain_failure(str(result.payload.get("error", "")))


@dataclass(frozen=True)
class RunFailure:
    """A failed run as the chat shows it: a title, one sentence, and whether Settings can fix it."""

    kind: str
    title: str
    detail: str
    fixed_in_settings: bool


# By failure_kinds: the title, the sentence (with {endpoint}), whether the Connection page can fix it.
RUN_FAILURES = {
    kinds.CONNECTION: (
        tr("No connection to the model"),
        tr("{endpoint} does not answer. Check that the server is running and the address is right."),
        True,
    ),
    kinds.TIMEOUT: (
        tr("The model took too long"),
        tr("No answer from {endpoint} in time. Try again, or pick a faster model."),
        False,
    ),
    kinds.AUTH: (tr("The key was not accepted"), tr("{endpoint} refused the API key. Check it in Settings."), True),
    kinds.QUOTA: (
        tr("The quota ran out"),
        tr("The provider refused: the account's limit or balance is used up."),
        False,
    ),
    kinds.BUSY: (
        tr("The model is overloaded"),
        tr("It stayed busy through every retry. Try again in a minute."),
        False,
    ),
    kinds.NOT_FOUND: (
        tr("Model or address not found"),
        tr("{endpoint} does not know this model or path. Check them in Settings."),
        True,
    ),
}
RUN_FAILED = tr("The request failed")
NOT_SET_UP = tr("The connection is not set up")


def explain_run_failure(kind: str, message: str, endpoint: str) -> RunFailure:
    """A failed run in plain words; a kind without its own sentence shows the message itself."""
    if kind == kinds.SETUP:
        return RunFailure(kind, NOT_SET_UP, str(message), True)
    if kind not in RUN_FAILURES:
        return RunFailure(kinds.OTHER, RUN_FAILED, str(message), False)
    title, detail, fixed_in_settings = RUN_FAILURES[kind]
    return RunFailure(kind, title, detail.format(endpoint=endpoint), fixed_in_settings)
