"""The open data the agent knows how to fetch: a fixed list, so every host it contacts is known in advance.

Vector sets download as GeoJSON from GitHub mirrors (the Natural Earth CDN was
too slow to rely on); imagery and rasters come from the Microsoft Planetary
Computer STAC API as cloud-optimised GeoTIFFs read in place.
"""

from dataclasses import dataclass, field

KIND_VECTOR = "vector"
KIND_IMAGERY = "imagery"
KIND_POINTER = "pointer"
TRUE_COLOR = "true_color"


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    kind: str
    summary: str
    coverage: str
    license: str
    keywords: tuple[str, ...]
    load_with: str = ""
    # Imagery: the STAC asset loaded by default, the ones offered, and whether scenes carry cloud cover.
    default_asset: str = ""
    assets: tuple[str, ...] = ()
    cloudy: bool = False
    # Assets stacked into one RGB layer for TRUE_COLOR when the collection has no ready-made picture.
    rgb: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())


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

DATASETS: tuple[Dataset, ...] = (
    Dataset(
        id="natural-earth",
        title="Natural Earth",
        kind=KIND_VECTOR,
        summary="World base layers: countries, provinces, cities, rivers, lakes, coastline, roads, railways, ports.",
        coverage="whole world, 1:10m / 1:50m / 1:110m",
        license="public domain",
        keywords=(
            "country",
            "countries",
            "border",
            "province",
            "state",
            "city",
            "cities",
            "capital",
            "river",
            "lake",
            "coast",
            "ocean",
            "land",
            "road",
            "railway",
            "airport",
            "port",
            "world",
            "admin",
        ),
        load_with="load_dataset",
        notes=(
            "layer: " + ", ".join(NATURAL_EARTH_LAYERS),
            "scale: 10m (detailed), 50m (default), 110m (world maps); roads, railroads, "
            "airports, ports and urban_areas exist at 10m only",
        ),
    ),
    Dataset(
        id="geoboundaries",
        title="geoBoundaries",
        kind=KIND_VECTOR,
        summary="Administrative boundaries of one country down to districts and municipalities.",
        coverage="every country; ADM0 country, ADM1 regions, ADM2 districts, ADM3+ where published",
        license="open, per country (returned with the data)",
        keywords=(
            "admin",
            "administrative",
            "boundary",
            "boundaries",
            "region",
            "district",
            "municipality",
            "county",
            "oblast",
            "province",
            "border",
        ),
        load_with="load_dataset",
        notes=("country: ISO 3166 alpha-3 code such as FRA or KEN", "level: ADM0 … ADM5"),
    ),
    Dataset(
        id="sentinel-2-l2a",
        title="Sentinel-2 Level-2A",
        kind=KIND_IMAGERY,
        summary="Optical satellite scenes, 10 m, atmospherically corrected, every few days since 2015.",
        coverage="all land, 2015 to now",
        license="Copernicus open licence",
        keywords=("satellite", "imagery", "image", "photo", "optical", "sentinel", "scene", "ndvi", "vegetation"),
        load_with="search_imagery, then load_imagery",
        default_asset="visual",
        assets=("visual", "B02", "B03", "B04", "B08", "B11", "B12", "SCL"),
        cloudy=True,
        notes=("visual is the ready true-colour picture; B04 red, B08 near infrared; SCL scene classes",),
    ),
    Dataset(
        id="landsat-c2-l2",
        title="Landsat Collection 2 Level-2",
        kind=KIND_IMAGERY,
        summary="Optical satellite scenes, 30 m, the longest record: Landsat 4 to 9.",
        coverage="all land, 1982 to now",
        license="public domain (USGS)",
        keywords=("satellite", "imagery", "image", "landsat", "history", "historical", "change", "optical"),
        load_with="search_imagery, then load_imagery",
        default_asset=TRUE_COLOR,
        assets=(TRUE_COLOR, "red", "green", "blue", "nir08", "swir16", "lwir11"),
        cloudy=True,
        rgb=("red", "green", "blue"),
        notes=("true_color stacks red, green and blue into one layer",),
    ),
    Dataset(
        id="cop-dem-glo-30",
        title="Copernicus DEM GLO-30",
        kind=KIND_IMAGERY,
        summary="Elevation model, 30 m: heights for relief, slope, hillshade, watersheds.",
        coverage="whole world",
        license="Copernicus DEM licence (free, attribution)",
        keywords=("elevation", "height", "dem", "relief", "terrain", "slope", "hillshade", "altitude", "topography"),
        load_with="search_imagery, then load_imagery",
        default_asset="data",
        assets=("data",),
        notes=("tiles of 1°×1°; load every tile the area needs",),
    ),
    Dataset(
        id="cop-dem-glo-90",
        title="Copernicus DEM GLO-90",
        kind=KIND_IMAGERY,
        summary="Elevation model, 90 m: the lighter choice for large regions.",
        coverage="whole world",
        license="Copernicus DEM licence (free, attribution)",
        keywords=("elevation", "height", "dem", "relief", "terrain", "topography"),
        load_with="search_imagery, then load_imagery",
        default_asset="data",
        assets=("data",),
    ),
    Dataset(
        id="esa-worldcover",
        title="ESA WorldCover",
        kind=KIND_IMAGERY,
        summary="Land cover classes at 10 m: forest, cropland, built-up, water and others, for 2020 and 2021.",
        coverage="whole world, 2020–2021",
        license="CC BY 4.0",
        keywords=("land cover", "landcover", "forest", "cropland", "built", "urban", "classification", "vegetation"),
        load_with="search_imagery, then load_imagery",
        default_asset="map",
        assets=("map",),
    ),
    Dataset(
        id="io-lulc-annual-v02",
        title="Esri 10m Annual Land Use Land Cover",
        kind=KIND_IMAGERY,
        summary="Yearly land use classes at 10 m, 2017–2023: compare years to see change.",
        coverage="whole world, 2017–2023",
        license="CC BY 4.0",
        keywords=("land use", "landuse", "land cover", "change", "urban growth", "deforestation"),
        load_with="search_imagery, then load_imagery",
        default_asset="data",
        assets=("data",),
    ),
    Dataset(
        id="jrc-gsw",
        title="JRC Global Surface Water",
        kind=KIND_IMAGERY,
        summary="Where and how often surface water was present, 1984–2020.",
        coverage="whole world",
        license="free, attribution",
        keywords=("water", "flood", "river", "lake", "wetland", "surface water", "hydrology"),
        load_with="search_imagery, then load_imagery",
        default_asset="occurrence",
        assets=("occurrence", "extent", "seasonality", "recurrence", "change", "transitions"),
    ),
    Dataset(
        id="openstreetmap",
        title="OpenStreetMap",
        kind=KIND_POINTER,
        summary="Detailed features by tag: buildings, roads, shops, amenities, land use, anything mapped.",
        coverage="whole world",
        license="ODbL",
        keywords=("osm", "building", "road", "street", "shop", "cafe", "amenity", "poi", "park", "school"),
        load_with="the osm skill (download_osm)",
    ),
    Dataset(
        id="basemaps",
        title="Basemaps",
        kind=KIND_POINTER,
        summary="Background maps and satellite basemaps to look at, not to analyse.",
        coverage="whole world",
        license="per provider",
        keywords=("basemap", "background", "satellite map", "topographic map", "tiles"),
        load_with="the project skill (add_basemap)",
    ),
)

BY_ID = {dataset.id: dataset for dataset in DATASETS}


def dataset(identifier: str, kind: str = "") -> Dataset:
    """The catalogue entry, or a ValueError listing what exists."""
    found = BY_ID.get(str(identifier or "").strip())
    if found is None or (kind and found.kind != kind):
        wanted = [item.id for item in DATASETS if not kind or item.kind == kind]
        raise ValueError(f"Unknown dataset '{identifier}'. Available: {', '.join(wanted)}. See find_open_data.")
    return found


def search(query: str) -> list[Dataset]:
    """Entries ranked by how many query words hit their keywords, title and summary; all of them for no query."""
    words = [word for word in str(query or "").lower().replace(",", " ").split() if len(word) > 1]
    if not words:
        return list(DATASETS)
    scored = []
    for item in DATASETS:
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
    return entry
