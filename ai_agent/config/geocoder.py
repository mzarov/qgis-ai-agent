import ipaddress
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from qgis.core import QgsSettings

SETTINGS_PREFIX = "ai_agent"
GEOCODER_DISABLED = "disabled"
GEOCODER_PHOTON = "photon"
GEOCODER_NOMINATIM = "nominatim"
GEOCODER_PHOTON_URL = "https://photon.komoot.io"
DEFAULT_GEOCODER_PROVIDER = GEOCODER_DISABLED
PUBLIC_OSMF_HOST = "nominatim.openstreetmap.org"
PUBLIC_OSMF_POLICY = "https://operations.osmfoundation.org/policies/nominatim/"
ALLOWED_PROVIDERS = {GEOCODER_DISABLED, GEOCODER_PHOTON, GEOCODER_NOMINATIM}
MAX_URL_CHARS = 4_096
LOCAL_SUFFIXES = (".internal", ".intranet", ".lan", ".local", ".localhost", ".home", ".corp")


def get_provider() -> str:
    value = QgsSettings().value(f"{SETTINGS_PREFIX}/geocoder_provider", DEFAULT_GEOCODER_PROVIDER, type=str)
    return value if isinstance(value, str) and value in ALLOWED_PROVIDERS else DEFAULT_GEOCODER_PROVIDER


def set_provider(value: str | None) -> None:
    selected = value if value in ALLOWED_PROVIDERS else DEFAULT_GEOCODER_PROVIDER
    _write("geocoder_provider", selected)


def get_custom_url() -> str:
    value = QgsSettings().value(f"{SETTINGS_PREFIX}/custom_nominatim_url", "", type=str)
    return value.strip() if isinstance(value, str) else ""


def set_custom_url(value: str | None) -> None:
    _write("custom_nominatim_url", (value or "").strip())


def get_url() -> str:
    provider = get_provider()
    if provider == GEOCODER_PHOTON:
        return GEOCODER_PHOTON_URL
    if provider == GEOCODER_NOMINATIM:
        return get_custom_url()
    return ""


def validated_service_url(raw: Any) -> str:
    service_url = str(raw or "").strip()
    if not service_url:
        raise ValueError("The URL is empty.")
    if len(service_url) > MAX_URL_CHARS:
        raise ValueError(f"The URL must not exceed {MAX_URL_CHARS} characters.")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in service_url):
        raise ValueError("The URL contains control or formatting characters.")
    try:
        parsed = urlsplit(service_url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
    except (UnicodeError, ValueError):
        raise ValueError("The URL is malformed; check its host, brackets and port.") from None
    if parsed.scheme.lower() != "https" or not host:
        raise ValueError("Geocoding services require a public https URL.")
    if parsed.username is not None or parsed.password is not None or parsed.query:
        raise ValueError("The geocoding service base URL must not contain credentials or query parameters.")
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or not _public_literal(host):
        raise ValueError("The geocoding service must use a public host.")
    if host == PUBLIC_OSMF_HOST:
        raise ValueError(
            "The public OSMF Nominatim endpoint is not built into this agent. "
            f"Use a service you are authorised to use; policy: {PUBLIC_OSMF_POLICY}"
        )
    shown_host = f"[{host}]" if ":" in host else host
    netloc = f"{shown_host}:{port}" if port is not None else shown_host
    return urlunsplit(("https", netloc, parsed.path.rstrip("/") or "/", "", ""))


def _public_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global and not any((address.is_private, address.is_loopback, address.is_link_local))


def _write(key: str, value: str) -> None:
    settings = QgsSettings()
    settings.setValue(f"{SETTINGS_PREFIX}/{key}", value)
    settings.sync()
