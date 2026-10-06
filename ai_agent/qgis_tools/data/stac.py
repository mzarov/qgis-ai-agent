"""Imagery from the Microsoft Planetary Computer STAC API: search scenes, read an item, sign its assets.

Assets live in Azure Blob Storage and open in place through GDAL's /vsicurl/
once a short-lived SAS token is appended; the token endpoint needs no account.
"""

import time
from typing import Any
from urllib.parse import quote, urlparse

from ai_agent.qgis_tools.data.http import get_json, post_json

STAC_ROOT = "https://planetarycomputer.microsoft.com/api/stac/v1"
# Tokens are per storage container, not per collection: one collection's token is refused by another account.
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
BLOB_SUFFIX = ".blob.core.windows.net"
CLOUD = "eo:cloud_cover"
# A cached token is replaced this long before it expires, so a layer never starts with a dying link.
TOKEN_MARGIN_S = 15 * 60
TOKEN_FALLBACK_S = 45 * 60
_tokens: dict[str, tuple[str, float, str]] = {}


def search(
    collection: str,
    bbox: tuple[float, float, float, float],
    dates: str,
    max_cloud: float | None,
    limit: int,
    newest_first: bool,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"collections": [collection], "bbox": list(bbox), "limit": limit}
    if dates:
        body["datetime"] = dates
    if max_cloud is not None:
        body["query"] = {CLOUD: {"lte": max_cloud}}
    field = "properties.datetime" if newest_first or max_cloud is None else f"properties.{CLOUD}"
    body["sortby"] = [{"field": field, "direction": "desc" if field.endswith("datetime") else "asc"}]
    answer = post_json(f"{STAC_ROOT}/search", body)
    return [_summary(feature) for feature in (answer.get("features") or [])[:limit]]


def item(collection: str, item_id: str) -> dict[str, Any]:
    found = get_json(f"{STAC_ROOT}/collections/{quote(collection)}/items/{quote(item_id, safe='')}")
    if not isinstance(found, dict) or not found.get("assets"):
        raise ValueError(f"Scene '{item_id}' was not found in {collection}. Use an id from search_imagery.")
    return found


def asset_href(found: dict[str, Any], asset: str) -> str:
    entry = (found.get("assets") or {}).get(asset)
    if not isinstance(entry, dict) or not entry.get("href"):
        offered = ", ".join(sorted(found.get("assets") or {}))
        raise ValueError(f"Scene '{found.get('id')}' has no asset '{asset}'. It offers: {offered}.")
    return str(entry["href"])


def signed(href: str) -> tuple[str, str]:
    """The asset link with a read token appended, and the token's expiry text."""
    token, expiry = sas_token(href)
    return f"{href}{'&' if '?' in href else '?'}{token}", expiry


def sas_token(href: str) -> tuple[str, str]:
    """A read token for the storage container behind `href`; reused while it has time left."""
    account, container = _container(href)
    key = f"{account}/{container}"
    cached = _tokens.get(key)
    if cached and cached[1] - time.time() > TOKEN_MARGIN_S:
        return cached[0], cached[2]
    answer = get_json(TOKEN_URL.format(account=quote(account), container=quote(container)))
    token = str((answer or {}).get("token") or "")
    if not token:
        raise ValueError("The Planetary Computer did not issue a read token. Retry in a minute.")
    expiry = str(answer.get("msft:expiry") or "")
    _tokens[key] = (token, _epoch(expiry) or time.time() + TOKEN_FALLBACK_S, expiry)
    return token, expiry


def _container(href: str) -> tuple[str, str]:
    parsed = urlparse(href)
    host = parsed.hostname or ""
    parts = [part for part in parsed.path.split("/") if part]
    if not host.endswith(BLOB_SUFFIX) or not parts:
        raise ValueError(f"The asset is not in Planetary Computer storage: {host}.")
    return host[: -len(BLOB_SUFFIX)], parts[0]


def scene_date(properties: dict[str, Any]) -> str:
    """The acquisition day; composites such as WorldCover carry a start date instead."""
    return str(properties.get("datetime") or properties.get("start_datetime") or "")[:10]


def _summary(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    summary: dict[str, Any] = {"id": feature.get("id"), "date": scene_date(properties)}
    if properties.get(CLOUD) is not None:
        summary["cloud_cover"] = round(float(properties[CLOUD]), 1)
    for key, label in (("platform", "platform"), ("s2:mgrs_tile", "tile"), ("landsat:wrs_path", "wrs_path")):
        if properties.get(key) is not None:
            summary[label] = properties[key]
    if properties.get("landsat:wrs_row") is not None:
        summary["wrs_row"] = properties["landsat:wrs_row"]
    if feature.get("bbox"):
        summary["bbox"] = [round(float(value), 4) for value in feature["bbox"][:4]]
    return summary


def _epoch(text: str) -> float:
    try:
        return time.mktime(time.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except (ValueError, OverflowError):
        return 0.0
