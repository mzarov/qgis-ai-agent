"""Public web map services the agent may add as layers: tiles, WMS and WFS, every address checked by hand.

Each worked without a key when added (2026-10). Services that refused or timed
out from a plain client then — IGN Spain, Terrascope, NRCan, INEGI, BKG — are
left out rather than shipped broken. A {date} in a tile template is filled at
load time (NASA GIBS daily imagery).
"""

from ai_agent.qgis_tools.data.dataset import (
    KIND_SERVICE,
    SERVICE_WFS,
    SERVICE_WMS,
    SERVICE_XYZ,
    Dataset,
    ServiceLayer,
)

GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{matrix}/{{z}}/{{y}}/{{x}}.{ext}"
GEOPF_TILE = (
    "https://data.geopf.fr/wmts?REQUEST=GetTile&SERVICE=WMTS&VERSION=1.0.0&STYLE=normal&TILEMATRIXSET=PM"
    "&FORMAT={format}&LAYER={layer}&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}"
)
ADMIN_EXPRESS = "ADMINEXPRESS-COG-CARTO.LATEST:{0}"

SERVICES: tuple[Dataset, ...] = (
    Dataset(
        id="opentopomap",
        title="OpenTopoMap",
        kind=KIND_SERVICE,
        summary="Topographic map of the world from OpenStreetMap and SRTM: contours, hillshade, paths.",
        coverage="whole world, to zoom 17",
        license="CC BY-SA (map style), ODbL (data)",
        keywords=("topographic", "topo", "contours", "hiking", "terrain map", "basemap"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(ServiceLayer("map", "Topographic map", "https://tile.opentopomap.org/{z}/{x}/{y}.png", zmax=17),),
        attribution="© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
    ),
    Dataset(
        id="nasa-gibs",
        title="NASA GIBS",
        kind=KIND_SERVICE,
        summary="NASA global imagery: yesterday's satellite picture of the whole Earth, night lights, Blue Marble.",
        coverage="whole world; daily since 2000 at about 250 m",
        license="public domain (NASA EOSDIS)",
        keywords=("satellite", "daily", "today", "yesterday", "modis", "night lights", "nasa", "fires", "clouds"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(
            ServiceLayer(
                "modis_true_color",
                "MODIS Terra true colour, daily",
                GIBS.format(
                    layer="MODIS_Terra_CorrectedReflectance_TrueColor",
                    time="{date}",
                    matrix="GoogleMapsCompatible_Level9",
                    ext="jpg",
                ),
                note="one day; pass date YYYY-MM-DD, default yesterday",
                zmax=9,
            ),
            ServiceLayer(
                "black_marble",
                "Night lights (VIIRS Black Marble 2016)",
                GIBS.format(
                    layer="VIIRS_Black_Marble", time="2016-01-01", matrix="GoogleMapsCompatible_Level8", ext="png"
                ),
                zmax=8,
            ),
            ServiceLayer(
                "blue_marble",
                "Blue Marble shaded relief and bathymetry",
                GIBS.format(
                    layer="BlueMarble_ShadedRelief_Bathymetry",
                    time="2004-08-01",
                    matrix="GoogleMapsCompatible_Level8",
                    ext="jpeg",
                ),
                zmax=8,
            ),
        ),
        attribution="NASA EOSDIS GIBS",
    ),
    Dataset(
        id="s2-cloudless",
        title="Sentinel-2 cloudless (EOX)",
        kind=KIND_SERVICE,
        summary="A seamless cloud-free mosaic of the world from Sentinel-2, 2024: the prettiest satellite backdrop.",
        coverage="whole world, 10 m, mosaic of 2024",
        license="CC BY-NC-SA 4.0: non-commercial use only",
        keywords=("satellite", "mosaic", "cloud free", "imagery", "backdrop", "sentinel"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(
            ServiceLayer(
                "mosaic_2024",
                "Sentinel-2 cloudless 2024",
                "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg",
                zmax=15,
            ),
        ),
        attribution="Sentinel-2 cloudless 2024 by EOX IT Services GmbH (contains modified Copernicus Sentinel data)",
        notes=("not for commercial use — say so when the user's work may be commercial",),
    ),
    Dataset(
        id="gebco",
        title="GEBCO bathymetry",
        kind=KIND_SERVICE,
        summary="Ocean depths and land heights of the whole planet as a shaded map.",
        coverage="whole world, about 450 m",
        license="free, attribution to GEBCO Compilation Group",
        keywords=("bathymetry", "ocean", "sea", "depth", "seafloor", "relief", "elevation"),
        load_with="load_service",
        service=SERVICE_WMS,
        endpoint="https://wms.gebco.net/mapserv",
        layers=(ServiceLayer("gebco", "GEBCO latest grid", "GEBCO_LATEST"),),
        attribution="GEBCO Compilation Group",
    ),
    Dataset(
        id="ign-france",
        title="IGN France",
        kind=KIND_SERVICE,
        summary="France: aerial photos, the Plan IGN map, and regions, departments and communes as vectors.",
        coverage="France including overseas",
        license="Licence Ouverte Etalab 2.0",
        keywords=("france", "french", "ign", "orthophoto", "aerial", "commune", "departement", "region", "cadastre"),
        load_with="load_service",
        service=SERVICE_XYZ,
        endpoint="https://data.geopf.fr/wfs",
        layers=(
            ServiceLayer(
                "orthophotos",
                "Aerial photos",
                GEOPF_TILE.format(format="image/jpeg", layer="ORTHOIMAGERY.ORTHOPHOTOS"),
                zmax=20,
            ),
            ServiceLayer(
                "plan_ign",
                "Plan IGN map",
                GEOPF_TILE.format(format="image/png", layer="GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"),
            ),
            ServiceLayer(
                "regions", "Regions (vector)", ADMIN_EXPRESS.format("region"), note="vector", protocol=SERVICE_WFS
            ),
            ServiceLayer(
                "departements",
                "Departments (vector)",
                ADMIN_EXPRESS.format("departement"),
                note="vector",
                protocol=SERVICE_WFS,
            ),
            ServiceLayer(
                "communes",
                "Communes (vector)",
                ADMIN_EXPRESS.format("commune"),
                note="vector, loads the map view only",
                protocol=SERVICE_WFS,
            ),
        ),
        attribution="IGN – Géoplateforme",
    ),
    Dataset(
        id="pdok",
        title="PDOK Netherlands",
        kind=KIND_SERVICE,
        summary="The Netherlands: current aerial photos, the BRT base map, provinces and municipalities.",
        coverage="the Netherlands",
        license="CC BY 4.0 / CC0",
        keywords=("netherlands", "dutch", "holland", "pdok", "aerial", "luchtfoto", "gemeente", "province"),
        load_with="load_service",
        service=SERVICE_XYZ,
        endpoint="https://service.pdok.nl/kadaster/bestuurlijkegebieden/wfs/v1_0",
        layers=(
            ServiceLayer(
                "aerial",
                "Aerial photos (current)",
                "https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg",
            ),
            ServiceLayer(
                "brt",
                "BRT base map",
                "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png",
            ),
            ServiceLayer(
                "provinces",
                "Provinces (vector)",
                "bestuurlijkegebieden:Provinciegebied",
                note="vector",
                protocol=SERVICE_WFS,
            ),
            ServiceLayer(
                "municipalities",
                "Municipalities (vector)",
                "bestuurlijkegebieden:Gemeentegebied",
                note="vector",
                protocol=SERVICE_WFS,
            ),
        ),
        attribution="PDOK / Kadaster",
    ),
    Dataset(
        id="swisstopo",
        title="swisstopo",
        kind=KIND_SERVICE,
        summary="Switzerland: the national map and SWISSIMAGE aerial photos.",
        coverage="Switzerland",
        license="free use with attribution (swisstopo)",
        keywords=("switzerland", "swiss", "swisstopo", "aerial", "national map"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(
            ServiceLayer(
                "national_map",
                "National map (colour)",
                "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg",
            ),
            ServiceLayer(
                "swissimage",
                "SWISSIMAGE aerial photos",
                "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg",
                zmax=20,
            ),
        ),
        attribution="© swisstopo",
    ),
    Dataset(
        id="usgs",
        title="USGS The National Map",
        kind=KIND_SERVICE,
        summary="The United States: aerial imagery and the US Topo map.",
        coverage="United States",
        license="public domain (USGS)",
        keywords=("usa", "united states", "america", "usgs", "aerial", "topo", "imagery"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(
            ServiceLayer(
                "imagery",
                "Aerial imagery",
                "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
                zmax=16,
            ),
            ServiceLayer(
                "topo",
                "US Topo",
                "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
                zmax=16,
            ),
        ),
        attribution="USGS The National Map",
    ),
    Dataset(
        id="ga-australia",
        title="Geoscience Australia",
        kind=KIND_SERVICE,
        summary="Australia: the national topographic base map.",
        coverage="Australia",
        license="CC BY 4.0",
        keywords=("australia", "australian", "topographic", "base map"),
        load_with="load_service",
        service=SERVICE_XYZ,
        layers=(
            ServiceLayer(
                "topographic",
                "Topographic base map",
                "https://services.ga.gov.au/gis/rest/services/Topographic_Base_Map/MapServer/tile/{z}/{y}/{x}",
                zmax=16,
            ),
            ServiceLayer(
                "national",
                "National base map",
                "https://services.ga.gov.au/gis/rest/services/NationalBaseMap/MapServer/tile/{z}/{y}/{x}",
                zmax=16,
            ),
        ),
        attribution="© Geoscience Australia",
    ),
)
