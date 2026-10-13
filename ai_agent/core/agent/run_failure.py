"""A failed run in words a person reads: a title, one sentence, and what can help.

The model request failing ends the turn, so the feed shows a card, not the raw
error (that stays one hover away). The kind comes from `llm/failure_kinds.py`;
whether the Connection page can fix it and whether simply sending again can
decide which buttons the card offers.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from ai_agent.core.llm import failure_kinds as kinds
from ai_agent.i18n import tr

CONFIGURED_ENDPOINT = tr("The configured server")


@dataclass(frozen=True)
class RunFailure:
    """A failed run as the chat shows it.

    `retry_helps` — sending the same request again may work (a server restarted, a busy
    model freed); a refused key or a wrong path fails the same way until the settings change.
    """

    kind: str
    title: str
    detail: str
    fixed_in_settings: bool
    retry_helps: bool


# By kind: the title; the sentence ({endpoint} is the host, {address} adds the path, {model} the model);
# whether the Connection page can fix it; whether sending again as it is may help.
RUN_FAILURES = {
    kinds.CONNECTION: (
        tr("No connection to the model"),
        tr("{endpoint} does not answer. Check that the server is running and the address is right."),
        True,
        True,
    ),
    kinds.TIMEOUT: (
        tr("The model took too long"),
        tr("No answer from {endpoint} in time. Try again, or pick a faster model."),
        False,
        True,
    ),
    kinds.AUTH: (
        tr("The key was not accepted"),
        tr("{endpoint} refused the API key. Check it in Settings."),
        True,
        False,
    ),
    kinds.QUOTA: (
        tr("The quota ran out"),
        tr("The provider refused: the account's limit or balance is used up."),
        False,
        True,
    ),
    kinds.BUSY: (
        tr("The model is overloaded"),
        tr("It stayed busy through every retry. Try again in a minute."),
        False,
        True,
    ),
    kinds.NOT_FOUND: (
        tr("Model or address not found"),
        tr("The server knows no such path or model. Check the address {address} and the model “{model}” in Settings."),
        True,
        False,
    ),
}
RUN_FAILED = tr("The request failed")
NOT_SET_UP = tr("The connection is not set up")


def explain_run_failure(kind: str, message: str, url: str = "", model: str = "") -> RunFailure:
    """A failed run in plain words; a kind without its own sentence shows the message itself."""
    if kind == kinds.SETUP:
        return RunFailure(kind, NOT_SET_UP, str(message), True, False)
    if kind not in RUN_FAILURES:
        return RunFailure(kinds.OTHER, RUN_FAILED, str(message), False, True)
    title, detail, fixed_in_settings, retry_helps = RUN_FAILURES[kind]
    shown = detail.format(endpoint=host_label(url), address=address_label(url), model=model)
    return RunFailure(kind, title, shown, fixed_in_settings, retry_helps)


def host_label(url: str) -> str:
    """`api.example.com:8443` — the server alone, no scheme, credentials or path."""
    host, _path = _parts(url)
    return host or CONFIGURED_ENDPOINT


def address_label(url: str) -> str:
    """`api.example.com/v1` — the server and the path, the part of an address a typo hides in."""
    host, path = _parts(url)
    return f"{host}{path}" if host else CONFIGURED_ENDPOINT


def _parts(url: str) -> tuple[str, str]:
    # The query and the fragment stay out: a key in `?key=` must not reach the screen.
    try:
        parsed = urlsplit((url or "").strip())
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        return "", ""
    host = parsed.hostname or ""
    return (f"{host}{port}" if host else ""), parsed.path.rstrip("/")
