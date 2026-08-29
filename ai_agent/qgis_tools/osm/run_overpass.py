from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.osm.args import geometry, wanted_name
from ai_agent.qgis_tools.osm.fetch import fetch
from ai_agent.qgis_tools.osm.load import SUBLAYERS, load_sublayers, write_payload
from ai_agent.qgis_tools.osm.overpass import RECURSE_DOWN

MAX_QUERY_CHARS = 4000
SHOWN_CHARS = 90
NOTHING_FOUND = (
    "Overpass ran fine, but the query produced no layer. Either nothing matches it, "
    "or the output statement leaves the geometry unresolved."
)
NO_OUTPUT = (
    "The query has no out statement, so Overpass would return nothing. "
    f"End it with '{RECURSE_DOWN}' and then 'out body;'."
)
SKELETON_OUTPUT = (
    "This query ends with a skeleton output. It prints ways before the nodes they are "
    "made of, and the OSM reader in QGIS reads the file in one pass — the layer would "
    f"come out empty. End the query with '{RECURSE_DOWN}' and then 'out body;' instead."
)


class RunOverpassTool(BaseTool):
    name = "run_overpass"
    description = (
        "Run a raw Overpass QL query and load whatever it returns as layers. This is the "
        "escape hatch for everything download_osm cannot express: around: radius searches, "
        "is_in, recursion upwards, unions of unrelated queries, filters by element count. "
        "Prefer download_osm for ordinary tag-in-a-territory requests — it is checked, "
        "summarised readably and harder to get wrong."
    )
    skill = "osm"
    safety = SAFETY_WRITE
    constraints = [
        "The whole query is yours: the header, the territory and the output statement",
        f"End it with '{RECURSE_DOWN}' and then 'out body;' or the geometry cannot be built",
        "Ask for xml output, not json: [out:xml]",
    ]
    examples = [
        "Find everything within 500 metres of the station",
        "Which district is this point in",
        "Streets that have no name",
    ]
    params_schema = [
        {
            "name": "query",
            "type": "string",
            "description": (
                "The complete Overpass QL query, header and output statement included. "
                f"Finish it with '{RECURSE_DOWN}' and then 'out body;' so the nodes arrive "
                "before the ways that use them."
            ),
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name for the result.",
            "required": True,
        },
        {
            "name": "intent",
            "type": "string",
            "description": "One plain-language line for the user: what this query fetches and why.",
            "required": True,
        },
        {
            "name": "geometry",
            "type": "string",
            "enum": sorted(SUBLAYERS),
            "description": "Which geometries to keep: points, lines, polygons, or all.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(params)
        prepared["intent"] = _checked_intent(params.get("intent"))
        prepared["query"] = _checked_query(params.get("query"))
        prepared["geometry"] = geometry(params)
        prepared["name"] = wanted_name(params)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        intent = str(params.get("intent") or "").strip() or _shortened(params.get("query"))
        return tr("Running an Overpass query for '{0}': {1}").format(wanted_name(params), intent)

    def detail_call(self, params: dict[str, Any]) -> str:
        return str(params.get("query") or "").strip()

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = _checked_query(params.get("query"))
        wanted = geometry(params)
        name = wanted_name(params)
        path = write_payload(fetch(query), name)
        loaded = load_sublayers(path, wanted, name)
        if not loaded:
            raise ValueError(NOTHING_FOUND)
        return {
            "layers": loaded,
            "total_features": sum(item["feature_count"] for item in loaded),
            "source": path,
        }


def _checked_intent(raw: Any) -> str:
    intent = str(raw or "").strip()
    if not intent:
        raise ValueError("intent is required: one plain line telling the user what this query fetches.")
    return intent


def _checked_query(raw: Any) -> str:
    query = str(raw or "").strip()
    if not query:
        raise ValueError("The query is empty. Write the whole Overpass QL statement.")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"The query is longer than {MAX_QUERY_CHARS} characters — simplify it.")
    if "out " not in query and "out;" not in query:
        raise ValueError(NO_OUTPUT)
    if "out skel" in query:
        raise ValueError(SKELETON_OUTPUT)
    return query


def _shortened(raw: Any) -> str:
    flat = " ".join(str(raw or "").split())
    return flat if len(flat) <= SHOWN_CHARS else flat[:SHOWN_CHARS] + "…"
