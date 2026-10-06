from typing import Any

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.data.catalogue import KIND_IMAGERY, dataset
from ai_agent.qgis_tools.data.region import region
from ai_agent.qgis_tools.data.stac import search

DEFAULT_LIMIT = 5
MAX_LIMIT = 10
DEFAULT_MAX_CLOUD = 20.0
LOAD_HINT = "load_imagery with collection={collection} and item_ids; default asset {asset}"
NOTHING = (
    "No scene matches. Widen the dates, raise max_cloud, or check that the area is on land "
    "and inside the dataset's coverage."
)


class SearchImageryTool(BaseTool):
    name = "search_imagery"
    description = (
        "Search satellite scenes and raster tiles (Sentinel-2, Landsat, elevation, land cover, "
        "surface water) over an area on the Microsoft Planetary Computer. Returns scene ids with "
        "date and cloud cover, for load_imagery."
    )
    skill = "data"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = True
    constraints = [
        "collection is a dataset id of kind imagery from find_open_data",
        "One area: bbox, bbox='canvas' or layer_name",
    ]
    examples = ["Find a cloud-free Sentinel-2 image of the current view from this summer", "Find DEM tiles for Crete"]
    params_schema = [
        {"name": "collection", "type": "string", "description": "Imagery dataset id, e.g. sentinel-2-l2a"},
        {
            "name": "bbox",
            "type": "string",
            "description": 'Area as "west,south,east,north" in degrees, or "canvas" for the current map view',
            "required": False,
        },
        params.layer_name("Search over this layer's extent instead of a bbox", required=False),
        {
            "name": "date_from",
            "type": "string",
            "description": "First day, YYYY-MM-DD; leave out for elevation and other timeless sets",
            "required": False,
        },
        {"name": "date_to", "type": "string", "description": "Last day, YYYY-MM-DD", "required": False},
        {
            "name": "max_cloud",
            "type": "number",
            "description": f"Highest cloud cover in percent for optical scenes; default {DEFAULT_MAX_CLOUD:.0f}",
            "required": False,
        },
        {
            "name": "newest_first",
            "type": "boolean",
            "description": "Sort by date instead of by clearest sky",
            "required": False,
        },
        {"name": "limit", "type": "integer", "description": f"Scenes to return, up to {MAX_LIMIT}", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        dataset(params.get("collection") or "", KIND_IMAGERY)
        region(params)
        _dates(params)
        return params

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Searching {0} scenes on the Planetary Computer.").format(str(params.get("collection") or ""))

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        scenes = payload.get("scenes") or []
        if not scenes:
            return tr("No scenes")
        count = tr_n("%n scene(s)", len(scenes))
        best = scenes[0]
        if "cloud_cover" in best:
            return tr("{0} · best {1}, {2}% cloud").format(count, best.get("date") or "", best["cloud_cover"])
        return tr("{0} · best {1}").format(count, best.get("date") or "")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = dataset(params.get("collection") or "", KIND_IMAGERY)
        bbox = region(params)
        max_cloud = float(params.get("max_cloud") or DEFAULT_MAX_CLOUD) if entry.cloudy else None
        limit = max(1, min(int(params.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
        scenes = search(entry.id, bbox, _dates(params), max_cloud, limit, bool(params.get("newest_first")))
        result: dict[str, Any] = {"collection": entry.id, "bbox": list(bbox), "scenes": scenes}
        if not scenes:
            result["note"] = NOTHING
        else:
            result["load_with"] = (
                f"load_imagery with collection={entry.id} and item_ids; default asset {entry.default_asset}"
            )
        return result


def _dates(params: dict[str, Any]) -> str:
    start = _day(params.get("date_from"), "date_from")
    end = _day(params.get("date_to"), "date_to")
    if not start and not end:
        return ""
    if start and end and start > end:
        raise ValueError(f"date_from {start} is after date_to {end}.")
    return f"{start + 'T00:00:00Z' if start else '..'}/{end + 'T23:59:59Z' if end else '..'}"


def _day(raw: Any, label: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = text.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts) or len(parts[0]) != 4:
        raise ValueError(f"{label} '{text}' is not a date like 2026-06-30.")
    return text
