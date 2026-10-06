"""The open data the agent knows how to fetch: a fixed list, so every host it contacts is known in advance.

Vector sets download as GeoJSON from GitHub mirrors (the Natural Earth CDN was
too slow to rely on); imagery and rasters come from the Microsoft Planetary
Computer STAC API as cloud-optimised GeoTIFFs read in place; web map services
are added as tile, WMS or WFS layers. The entries live in one JSON file per
connector (connectors.py), and the user can turn each connector off.
"""

from ai_agent.config.connectors import disabled_connectors
from ai_agent.qgis_tools.data.connectors import DATASETS, connector_of
from ai_agent.qgis_tools.data.dataset import (
    KIND_IMAGERY,
    KIND_POINTER,
    KIND_SERVICE,
    KIND_VECTOR,
    TRUE_COLOR,
    Dataset,
)

__all__ = ["DATASETS", "KIND_IMAGERY", "KIND_POINTER", "KIND_SERVICE", "KIND_VECTOR", "TRUE_COLOR", "Dataset"]
TURNED_OFF = (
    "The {connector} connector is turned off in Settings → Connectors, so its data is not available. "
    "Tell the user; they can turn it on there."
)

NATURAL_EARTH_LAYERS = {
    "countries": "admin_0_countries",
    "states_provinces": "admin_1_states_provinces",
    "populated_places": "populated_places",
    "rivers": "rivers_lake_centerlines",
    "lakes": "lakes",
    "coastline": "coastline",
    "land": "land",
    "ocean": "ocean",
    "urban_areas": "urban_areas",
    "roads": "roads",
    "railroads": "railroads",
    "airports": "airports",
    "ports": "ports",
}
NATURAL_EARTH_SCALES = ("10m", "50m", "110m")
# Layers Natural Earth publishes only at the most detailed scale.
NATURAL_EARTH_10M_ONLY = frozenset({"urban_areas", "roads", "railroads", "airports", "ports"})
GEOBOUNDARIES_LEVELS = ("ADM0", "ADM1", "ADM2", "ADM3", "ADM4", "ADM5")

BY_ID = {dataset.id: dataset for dataset in DATASETS}


def is_enabled(item: Dataset) -> bool:
    connector = connector_of(item.id)
    return connector is None or connector.id not in disabled_connectors()


def dataset(identifier: str, kind: str = "") -> Dataset:
    """The catalogue entry, or a ValueError listing what exists."""
    found = BY_ID.get(str(identifier or "").strip())
    if found is None or (kind and found.kind != kind):
        wanted = [item.id for item in DATASETS if (not kind or item.kind == kind) and is_enabled(item)]
        raise ValueError(f"Unknown dataset '{identifier}'. Available: {', '.join(wanted)}. See find_open_data.")
    if not is_enabled(found):
        connector = connector_of(found.id)
        raise ValueError(TURNED_OFF.format(connector=connector.title if connector else found.title))
    return found


def search(query: str) -> list[Dataset]:
    """Entries ranked by how many query words hit their keywords, title and summary; all of them for no query."""
    words = [word for word in str(query or "").lower().replace(",", " ").split() if len(word) > 1]
    offered = [item for item in DATASETS if is_enabled(item)]
    if not words:
        return offered
    scored = []
    for item in offered:
        text = " ".join((item.id, item.title, item.summary, *item.keywords)).lower()
        score = sum(2 if word in item.keywords else 1 for word in words if word in text)
        if score:
            scored.append((score, item))
    return [item for _score, item in sorted(scored, key=lambda pair: -pair[0])]


def describe(item: Dataset) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": item.id,
        "title": item.title,
        "kind": item.kind,
        "summary": item.summary,
        "coverage": item.coverage,
        "license": item.license,
        "load_with": item.load_with,
    }
    if item.assets:
        entry["assets"] = list(item.assets)
        entry["default_asset"] = item.default_asset
    if item.cloudy:
        entry["cloud_filter"] = True
    if item.notes:
        entry["notes"] = list(item.notes)
    if item.layers:
        entry["layers"] = [
            {"key": layer.key, "title": layer.title, **({"note": layer.note} if layer.note else {})}
            for layer in item.layers
        ]
    connector = connector_of(item.id)
    if connector is not None:
        entry["connector"] = connector.title
    return entry
