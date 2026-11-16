from dataclasses import dataclass
from typing import Any

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.background import Background, InTask
from ai_agent.qgis_tools.osm.args import (
    CANVAS,
    as_text,
    geometry,
    required_key,
    selectors,
    territory,
    wanted_name,
)
from ai_agent.qgis_tools.osm.fetch import fetch_anywhere
from ai_agent.qgis_tools.osm.load import SUBLAYERS, load_answer
from ai_agent.qgis_tools.osm.overpass import build_query, endpoints, require_connector
from ai_agent.qgis_tools.osm.territory import (
    PROVIDER_KEY,
    URL_KEY,
    Geocoder,
    Territory,
    configured_geocoder,
    locate,
    pinned_geocoder,
    planned_geocoder,
)

NOTHING_FOUND = (
    "Overpass ran fine, but nothing matches this query. Either the tag is wrong — "
    "OSM keys and values are English, amenity=cafe — or nothing of that kind is mapped there."
)
NOTHING_IN_BBOX = " Change the tag or widen the bbox."
NOTHING_BY_NAME = (
    " Or no territory carries exactly this name: area is matched whole against name, name:en "
    "and int_name, so 'Berlin' works and 'Berlin, Germany' does not. Change the tag, pass the "
    'bare place name, or pass a bbox ("canvas" is the current map view).'
)
GEOCODER_HINT = (
    " With a geocoder chosen in Settings → Geocoding the place would be looked up instead of "
    "matched by name; the user can switch one on."
)
NOTHING_IN_PLACE = (
    " The search ran in '{found}', the place the geocoder returned for area. If that is the "
    "wrong place, add the region or the country to area, or pass a bbox; otherwise change the tag."
)


@dataclass(frozen=True)
class _Job:
    key: str
    value: str
    selectors: tuple[str, ...]
    geometry: str
    name: str
    area: str
    bbox: tuple[float, float, float, float] | None
    urls: tuple[str, ...]
    geocoder: Geocoder | None

    # Safe off the main thread: everything it needs was read when the job was made.
    def fetched(self, feedback: Any = None) -> tuple[str, Territory]:
        where = locate(self.area, self.bbox, self.geocoder, feedback)
        query = build_query(
            self.key, self.value, where.area, where.bbox, self.geometry, list(self.selectors), where.area_id
        )
        return fetch_anywhere(query, self.urls, feedback), where

    def loaded(self, found: tuple[str, Territory]) -> dict[str, Any]:
        text, where = found
        payload = load_answer(text, self.geometry, self.name, self._nothing_found(where))
        if where.found:
            payload["territory"] = where.found
        return payload

    def _nothing_found(self, where: Territory) -> str:
        if where.found:
            return NOTHING_FOUND + NOTHING_IN_PLACE.format(found=where.found)
        if not where.area:
            return NOTHING_FOUND + NOTHING_IN_BBOX
        return NOTHING_FOUND + NOTHING_BY_NAME + ("" if self.geocoder else GEOCODER_HINT)


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
    network_access = True
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
        require_connector()
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
        # Only Settings name the geocoder: whatever came in under these keys is dropped.
        prepared.pop(PROVIDER_KEY, None)
        prepared.pop(URL_KEY, None)
        geocoder = configured_geocoder() if area else None
        if geocoder is not None:
            prepared.update({PROVIDER_KEY: geocoder.provider, URL_KEY: geocoder.url})
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = wanted_name(params)
        where = (params.get("area") or "").strip() or tr("the given extent")
        geocoder = pinned_geocoder(params)
        if geocoder is None:
            return tr("Downloading '{0}' ({1}) from OSM in {2}.").format(name, _what(params), where)
        return tr("Downloading '{0}' ({1}) from OSM in {2}, located with {3}.").format(
            name, _what(params), where, geocoder.host
        )

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        return tr_n("%n feature(s)", int(payload.get("total_features") or 0))

    def start(self, params: dict[str, Any]) -> Background:
        job = _job(params)
        return InTask(self.summarize_call(params), job.fetched, job.loaded)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        job = _job(params)
        return job.loaded(job.fetched())


def _job(params: dict[str, Any]) -> _Job:
    require_connector()
    chosen = selectors(params)
    area, bbox = territory(params)
    return _Job(
        key="" if chosen else required_key(params),
        value=params.get("value") or "",
        selectors=tuple(chosen),
        geometry=geometry(params),
        name=wanted_name(params),
        area=area,
        bbox=bbox,
        urls=endpoints(),
        geocoder=planned_geocoder(params) if area else None,
    )


def _what(params: dict[str, Any]) -> str:
    chosen = params.get("selectors") or []
    if chosen:
        return "; ".join(str(item) for item in chosen)
    key = (params.get("key") or "").strip()
    value = (params.get("value") or "").strip()
    if not key:
        return tr("no tag")
    return f"{key}={value}" if value else key
