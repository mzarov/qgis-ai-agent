from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.osm.args import (
    CANVAS,
    as_text,
    geometry,
    required_key,
    selectors,
    territory,
    wanted_name,
)
from ai_agent.qgis_tools.osm.fetch import fetch
from ai_agent.qgis_tools.osm.load import SUBLAYERS, load_sublayers, write_payload
from ai_agent.qgis_tools.osm.overpass import build_query

NOTHING_FOUND = (
    "Overpass ran fine, but nothing matches this query. Either the tag is wrong — "
    "OSM keys and values are English, amenity=cafe — or nothing of that kind is "
    "mapped there. Retrying the same territory under a different spelling will not "
    "help: the name is already matched against name, name:en and int_name. Change "
    "the tag, widen the territory, or pass a bbox."
)


class DownloadOsmTool(BaseTool):
    name = "download_osm"
    description = (
        "Download OpenStreetMap data through Overpass and add it to the project as layers. "
        "The simple case is a key-value pair such as amenity=cafe. The hard case is a list "
        "of Overpass selectors: several tags at once, regular expressions, exclusions. "
        "The territory is given as a place name or as a rectangle."
    )
    skill = "osm"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "Either area or bbox is required — without a territory the query does not run",
        "OSM keys and values are written in English: amenity=cafe, highway=primary",
        "key with value, or selectors — one of the two",
    ]
    examples = [
        "Download the cafes in Berlin",
        "Load the roads in the current map view",
        "Download cafes, restaurants and bars as one layer",
        "All roads except the unpaved ones",
    ]
    params_schema = [
        {
            "name": "key",
            "type": "string",
            "description": (
                "OSM key for the simple case: amenity, highway, building, landuse. For anything harder use selectors."
            ),
            "required": False,
        },
        {
            "name": "value",
            "type": "string",
            "description": (
                "Value of the key: cafe, primary, residential. Without it every object carrying that key is taken."
            ),
            "required": False,
        },
        {
            "name": "area",
            "type": "string",
            "description": (
                "Name of the territory in OSM: Berlin, Île-de-France, Kyoto. Mutually exclusive with bbox."
            ),
            "required": False,
        },
        {
            "name": "bbox",
            "type": "string",
            "description": (
                f'A "west,south,east,north" rectangle in EPSG:4326 degrees, or "{CANVAS}" for the current map view.'
            ),
            "required": False,
        },
        {
            "name": "selectors",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Overpass selectors, one per list entry, for example "
                "[\"node['amenity'~'cafe|restaurant']\", \"way['shop']\"]. "
                "This expresses everything a key-value pair cannot: several tags, "
                "regular expressions, exclusions through != and !~. "
                "The plugin appends the territory, the timeout and the output — do not pass those."
            ),
            "required": False,
        },
        {
            "name": "geometry",
            "type": "string",
            "enum": sorted(SUBLAYERS),
            "description": ("Which geometries to load: points, lines, polygons, or all for everything that was found."),
            "required": False,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name. By default it is built from the key and the value.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        chosen = selectors(params)
        prepared = dict(params)
        prepared["key"] = "" if chosen else required_key(params)
        prepared["selectors"] = chosen
        prepared["geometry"] = geometry(params)
        prepared["name"] = wanted_name(params)
        area, bbox = territory(params)
        prepared["area"] = area
        prepared["bbox"] = as_text(bbox) if bbox else ""
        build_query(prepared["key"], params.get("value") or "", area, bbox, prepared["geometry"], chosen)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = wanted_name(params)
        where = (params.get("area") or "").strip() or tr("the given extent")
        return tr("Downloading '{0}' ({1}) from OSM in {2}.").format(name, _what(params), where)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        chosen = selectors(params)
        key = "" if chosen else required_key(params)
        wanted = geometry(params)
        name = wanted_name(params)
        area, bbox = territory(params)
        query = build_query(key, params.get("value") or "", area, bbox, wanted, chosen)
        path = write_payload(fetch(query), name)
        loaded = load_sublayers(path, wanted, name)
        if not loaded:
            raise ValueError(NOTHING_FOUND)
        return {
            "layers": loaded,
            "total_features": sum(item["feature_count"] for item in loaded),
            "source": path,
        }


def _what(params: dict[str, Any]) -> str:
    chosen = params.get("selectors") or []
    if chosen:
        return "; ".join(str(item) for item in chosen)
    key = (params.get("key") or "").strip()
    value = (params.get("value") or "").strip()
    if not key:
        return tr("no tag")
    return f"{key}={value}" if value else key
