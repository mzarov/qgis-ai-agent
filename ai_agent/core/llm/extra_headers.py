import re

from ai_agent.i18n import tr

MAX_HEADERS = 20
MAX_VALUE = 1024
NAME_PATTERN = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
# Headers the transport sets itself, and those that would carry a credential into config.
RESERVED = frozenset(
    {
        "anthropic-version",
        "api-key",
        "authorization",
        "connection",
        "content-length",
        "content-type",
        "cookie",
        "host",
        "proxy-authorization",
        "transfer-encoding",
        "x-api-key",
    }
)
SECRET_WORDS = ("auth", "cookie", "key", "password", "secret", "session", "token")
BAD_LINE = tr("Line {0}: write a header as Name: value.")
BAD_NAME = tr("Line {0}: «{1}» is not a header name.")
TAKEN = tr("Line {0}: the plugin sets {1} itself.")
SECRET = tr("Line {0}: {1} looks like it carries a key. Keys go in the API key field, which keeps them encrypted.")
TOO_MANY = tr("At most {0} headers.")
BAD_VALUE = tr("Line {0}: the value must be plain text of at most {1} characters.")


def parse(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for number, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition(":")
        name, value = name.strip(), value.strip()
        if not separator or not name or not value:
            raise ValueError(BAD_LINE.format(number))
        if not NAME_PATTERN.match(name):
            raise ValueError(BAD_NAME.format(number, name))
        lowered = name.lower()
        if lowered in RESERVED:
            raise ValueError(TAKEN.format(number, name))
        if any(word in lowered for word in SECRET_WORDS):
            raise ValueError(SECRET.format(number, name))
        if len(value) > MAX_VALUE or any(ord(character) < 32 for character in value):
            raise ValueError(BAD_VALUE.format(number, MAX_VALUE))
        headers[name] = value
        if len(headers) > MAX_HEADERS:
            raise ValueError(TOO_MANY.format(MAX_HEADERS))
    return headers


def lenient(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in (text or "").splitlines():
        try:
            headers.update(parse(line))
        except ValueError:
            continue
    return dict(list(headers.items())[:MAX_HEADERS])
