"""Connectors: the sources of the open-data catalogue as the user sees and switches them in Settings.

A connector is one provider — NASA, IGN France — with the datasets it serves.
Turning one off hides its datasets from the agent and refuses loading them.
"""

from dataclasses import dataclass

CATEGORY_WORLD = "world"
CATEGORY_IMAGERY = "imagery"
CATEGORY_TERRAIN = "terrain"
CATEGORY_PEOPLE = "people"
CATEGORY_NATIONAL = "national"
CATEGORIES = (CATEGORY_WORLD, CATEGORY_IMAGERY, CATEGORY_TERRAIN, CATEGORY_PEOPLE, CATEGORY_NATIONAL)


@dataclass(frozen=True)
class Connector:
    id: str
    title: str
    category: str
    summary: str
    datasets: tuple[str, ...]
    hosts: tuple[str, ...]


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        "openstreetmap",
        "OpenStreetMap",
        CATEGORY_WORLD,
        "Roads, buildings and places by tag, worldwide",
        ("openstreetmap", "basemaps"),
        ("overpass-api.de", "tile.openstreetmap.org"),
    ),
    Connector(
        "natural-earth",
        "Natural Earth",
        CATEGORY_WORLD,
        "Small tidy world layers: countries, rivers, cities",
        ("natural-earth",),
        ("raw.githubusercontent.com",),
    ),
    Connector(
        "opentopomap",
        "OpenTopoMap",
        CATEGORY_WORLD,
        "Topographic world map with contours",
        ("opentopomap",),
        ("tile.opentopomap.org",),
    ),
    Connector(
        "planetary-computer",
        "Microsoft Planetary Computer",
        CATEGORY_IMAGERY,
        "Sentinel-2, Landsat, elevation and land cover scenes",
        (
            "sentinel-2-l2a",
            "landsat-c2-l2",
            "cop-dem-glo-30",
            "cop-dem-glo-90",
            "esa-worldcover",
            "io-lulc-annual-v02",
            "jrc-gsw",
        ),
        ("planetarycomputer.microsoft.com", "blob.core.windows.net"),
    ),
    Connector(
        "nasa-gibs",
        "NASA GIBS",
        CATEGORY_IMAGERY,
        "Yesterday's Earth from space, night lights, Blue Marble",
        ("nasa-gibs",),
        ("gibs.earthdata.nasa.gov",),
    ),
    Connector(
        "eox",
        "EOX Sentinel-2 cloudless",
        CATEGORY_IMAGERY,
        "Cloud-free satellite mosaic of the world",
        ("s2-cloudless",),
        ("tiles.maps.eox.at",),
    ),
    Connector(
        "gebco",
        "GEBCO",
        CATEGORY_TERRAIN,
        "Ocean depths and land heights",
        ("gebco",),
        ("wms.gebco.net",),
    ),
    Connector(
        "geoboundaries",
        "geoBoundaries",
        CATEGORY_PEOPLE,
        "Administrative boundaries of every country",
        ("geoboundaries",),
        ("www.geoboundaries.org", "github.com"),
    ),
    Connector(
        "ign-france",
        "IGN France",
        CATEGORY_NATIONAL,
        "France: aerial photos, maps, communes",
        ("ign-france",),
        ("data.geopf.fr",),
    ),
    Connector(
        "pdok",
        "PDOK Netherlands",
        CATEGORY_NATIONAL,
        "Netherlands: aerial photos, base map, municipalities",
        ("pdok",),
        ("service.pdok.nl",),
    ),
    Connector(
        "swisstopo",
        "swisstopo",
        CATEGORY_NATIONAL,
        "Switzerland: national map and aerial photos",
        ("swisstopo",),
        ("wmts.geo.admin.ch",),
    ),
    Connector(
        "usgs",
        "USGS The National Map",
        CATEGORY_NATIONAL,
        "United States: aerial imagery and US Topo",
        ("usgs",),
        ("basemap.nationalmap.gov",),
    ),
    Connector(
        "ga-australia",
        "Geoscience Australia",
        CATEGORY_NATIONAL,
        "Australia: topographic base maps",
        ("ga-australia",),
        ("services.ga.gov.au",),
    ),
)

_OWNER = {dataset: connector for connector in CONNECTORS for dataset in connector.datasets}


def connector_of(dataset_id: str) -> Connector | None:
    return _OWNER.get(dataset_id)
