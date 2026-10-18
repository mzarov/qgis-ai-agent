import re
from contextlib import suppress
from typing import Any
from urllib.parse import quote, unquote

from qgis.core import QgsMapLayer, QgsVectorLayer

SECRET_KEYS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "authorization",
)
SIGNED_QUERY_KEYS = (
    "key",
    "sig",
    "signature",
    "x-amz-signature",
    "x-amz-credential",
    "x-goog-signature",
    "credential",
    "access_key",
    "awsaccesskeyid",
    "sas",
)
SECRET_NAMES = frozenset(name.replace("-", "_") for name in SECRET_KEYS + SIGNED_QUERY_KEYS)
# Spellings of the same secrets: x-api-key, subscription-key, x-amz-security-token, private_token.
SECRET_NAME_SUFFIXES = ("_key", "_token", "_secret", "_password", "_signature", "_credential")
SECRET_PATTERN = re.compile(r"(?i)\b(" + "|".join(SECRET_KEYS) + r")\s*=\s*('[^']*'|\"[^\"]*\"|[^\s&;]+)")
# A query or provider-URI parameter; its value may itself be a percent-encoded URL with a query.
QUERY_ITEM_PATTERN = re.compile(r"(^|[?&])([^=&?#\s'\"]+)=([^&#\s'\"]*)")
URL_USERINFO_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)([^/@\s]+@)")
MASKED_VALUE = "<hidden>"
MAX_SOURCE_CHARS = 300
# An XYZ URI nests a tile URL, and a proxy URL may nest one more; anything deeper is hidden unread.
MAX_NESTING = 4


def sanitize_source(source: str) -> str:
    if not source:
        return ""
    cleaned = _scrubbed(source, 0)
    if len(cleaned) > MAX_SOURCE_CHARS:
        return cleaned[:MAX_SOURCE_CHARS] + "…"
    return cleaned


def _scrubbed(text: str, depth: int) -> str:
    """Credentials masked in a URL, a provider URI or a connection string, and in the URIs encoded inside it."""
    cleaned = URL_USERINFO_PATTERN.sub(lambda m: f"{m.group(1)}{MASKED_VALUE}@", text)
    cleaned = SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={MASKED_VALUE}", cleaned)
    return QUERY_ITEM_PATTERN.sub(lambda m: _scrubbed_item(m, depth), cleaned)


def _scrubbed_item(match: re.Match[str], depth: int) -> str:
    lead, name, value = match.groups()
    if _is_secret_name(name):
        return f"{lead}{name}={MASKED_VALUE}"
    return f"{lead}{name}={_scrubbed_value(value, depth)}"


def _scrubbed_value(value: str, depth: int) -> str:
    """A nested URI decoded, scrubbed and encoded again as QgsDataSourceUri encodes it; a clean value as it was."""
    if depth >= MAX_NESTING:
        return MASKED_VALUE
    decoded = unquote(value)
    scrubbed = _scrubbed(decoded, depth + 1)
    if scrubbed == decoded:
        return value
    if decoded == value:
        return scrubbed
    # The mask stays readable; everything around it is encoded whole, as QGIS writes the URI.
    return MASKED_VALUE.join(quote(part, safe="") for part in scrubbed.split(MASKED_VALUE))


def _is_secret_name(name: str) -> bool:
    # `http-header:x-api-key=…` is how a QGIS URI keeps a request header: the header's name decides.
    plain = unquote(name).strip().lower().replace("-", "_").rsplit(":", 1)[-1]
    return plain in SECRET_NAMES or plain.endswith(SECRET_NAME_SUFFIXES)


def provider_name(layer: QgsMapLayer) -> str:
    for getter in ("providerType", "dataProvider"):
        with suppress(Exception):
            value = getattr(layer, getter)()
            if isinstance(value, str):
                return value
            return value.name()
    return ""


def layer_source(layer: QgsMapLayer) -> str:
    try:
        return sanitize_source(layer.source() or "")
    except Exception:
        return ""


def is_valid(layer: QgsMapLayer) -> bool:
    try:
        return bool(layer.isValid())
    except Exception:
        return True


def subset_filter(layer: QgsMapLayer) -> str:
    if not isinstance(layer, QgsVectorLayer):
        return ""
    try:
        return layer.subsetString() or ""
    except Exception:
        return ""


def selected_count(layer: QgsMapLayer) -> int | None:
    if not isinstance(layer, QgsVectorLayer):
        return None
    try:
        return int(layer.selectedFeatureCount())
    except Exception:
        return None


def layer_opacity(layer: QgsMapLayer) -> float | None:
    try:
        return round(float(layer.opacity()), 3)
    except Exception:
        return None


def describe_source(layer: QgsMapLayer) -> dict[str, Any]:
    info: dict[str, Any] = {
        "provider": provider_name(layer),
        "source": layer_source(layer),
        "is_valid": is_valid(layer),
    }
    if not info["is_valid"]:
        info["warning"] = (
            "The layer failed to load: the source is unreachable or the path is broken. "
            "Processing and styling will not work on it."
        )
    filter_expression = subset_filter(layer)
    if filter_expression:
        info["subset_filter"] = filter_expression
        info["filter_note"] = "The feature count above already reflects this filter."
    selected = selected_count(layer)
    if selected:
        info["selected_count"] = selected
    opacity = layer_opacity(layer)
    if opacity is not None and opacity < 1.0:
        info["opacity"] = opacity
    return info
