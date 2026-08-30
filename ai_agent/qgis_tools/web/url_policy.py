import ipaddress
import unicodedata
from urllib.parse import quote, urlsplit, urlunsplit

BLOCKED_HOST_SUFFIXES = (".internal", ".lan", ".local", ".localhost")
SECRET_QUERY_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "credential",
    "key",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "sig",
    "signature",
    "token",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-api-key",
    "x-goog-credential",
    "x-goog-signature",
}
SECRET_QUERY_SUFFIXES = ("_credential", "_password", "_secret", "_signature", "_token")
MAX_URL_CHARS = 4096


def canonical_host(host: str) -> str:
    normalized = (host or "").strip().lower().rstrip(".")
    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        pass
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("The URL contains an invalid international host name.") from None


def encoded(value: str) -> str:
    return quote(str(value or ""), safe="")


def safe_url_label(url: str) -> str:
    raw = str(url or "").strip()
    if len(raw) > MAX_URL_CHARS or unsafe_text_control(raw):
        return "configured web address"
    try:
        parsed = urlsplit(raw)
        host = canonical_host(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        return "configured web address"
    if not host:
        return "configured web address"
    return urlunsplit((parsed.scheme or "https", netloc(host, port), parsed.path or "/", "", ""))


def bounded_text(raw: object, label: str, limit: int) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"The {label} is empty.")
    if len(value) > limit:
        raise ValueError(f"The {label} must not exceed {limit} characters.")
    if unsafe_text_control(value):
        raise ValueError(f"The {label} contains control or formatting characters.")
    return value


def short_text(raw: object, limit: int = 160) -> str:
    value = str(raw or "").strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def unsafe_text_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def has_secret_query(keys: set[str]) -> bool:
    return any(key in SECRET_QUERY_KEYS or key.endswith(SECRET_QUERY_SUFFIXES) for key in keys)


def require_allowed_host_syntax(host: str, error: str) -> None:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized == "localhost" or normalized.endswith(BLOCKED_HOST_SUFFIXES) or "%" in normalized:
        raise ValueError(error)
    try:
        literal = ipaddress.ip_address(normalized)
    except ValueError:
        return
    if not is_public_address(literal):
        raise ValueError(error)


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.is_site_local:
        return False
    if address.is_multicast:
        return False
    if address.is_private or address.is_loopback or address.is_link_local:
        return False
    if address.is_reserved or address.is_unspecified or not address.is_global:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped is None or is_public_address(mapped)


def address_sort_key(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[int, int]:
    return (address.version, int(address))


def origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), canonical_host(parsed.hostname or ""), parsed.port or 443)


def pinned_url(url: str, address: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(("https", netloc(address, parsed.port), parsed.path or "/", parsed.query, ""))


def host_header(host: str, port: int | None) -> str:
    return netloc(host, None if port in (None, 443) else port)


def netloc(host: str, port: int | None) -> str:
    shown = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{shown}:{port}" if port else shown
