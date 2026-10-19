import time
from typing import Any
from urllib.parse import quote, urlparse

from ai_agent.qgis_tools.common.http import get_json, post_json
from ai_agent.qgis_tools.data.coverage import FULL_COVER, covered_share

STAC_ROOT = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS_ENDPOINT = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
BLOB_SUFFIX = ".blob.core.windows.net"
CLOUD = "eo:cloud_cover"
TOKEN_MARGIN_S = 15 * 60
TOKEN_FALLBACK_S = 45 * 60
MAX_FETCHED = 30
_tokens: dict[str, tuple[str, float, str]] = {}


def search(
    collection: str,
    bbox: tuple[float, float, float, float],
    dates: str,
    max_cloud: float | None,
    limit: int,
    newest_first: bool,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"collections": [collection], "bbox": list(bbox), "limit": min(MAX_FETCHED, limit * 3)}
    if dates:
        body["datetime"] = dates
    if max_cloud is not None:
        body["query"] = {CLOUD: {"lte": max_cloud}}
    field = "properties.datetime" if newest_first or max_cloud is None else f"properties.{CLOUD}"
    body["sortby"] = [{"field": field, "direction": "desc" if field.endswith("datetime") else "asc"}]
    answer = post_json(f"{STAC_ROOT}/search", body)
    scenes = [_summary(feature, bbox) for feature in answer.get("features") or []]
    scenes.sort(key=lambda scene: (scene.get("covers_area_percent") or 0) < FULL_COVER)
    return scenes[:limit]


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
    token, expiry = sas_token(href)
    return f"{href}{'&' if '?' in href else '?'}{token}", expiry


def sas_token(href: str) -> tuple[str, str]:
    account, container = _container(href)
    key = f"{account}/{container}"
    cached = _tokens.get(key)
    if cached and cached[1] - time.time() > TOKEN_MARGIN_S:
        return cached[0], cached[2]
    answer = get_json(SAS_ENDPOINT.format(account=quote(account), container=quote(container)))
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
    return str(properties.get("datetime") or properties.get("start_datetime") or "")[:10]


def _summary(feature: dict[str, Any], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    summary: dict[str, Any] = {"id": feature.get("id"), "date": scene_date(properties)}
    share = covered_share(feature.get("geometry"), bbox)
    if share is not None:
        summary["covers_area_percent"] = share
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
