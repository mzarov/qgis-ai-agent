BUILTIN_PROVIDERS = frozenset({"native", "qgis", "gdal"})

# Processing has no "modifies its input" flag: these write through their input parameters.
SOURCE_WRITERS = frozenset(
    {
        "native:truncatetable",
        "native:createattributeindex",
        "native:createspatialindex",
        "native:zonalstatistics",
        "native:repairshapefile",
        "native:definecurrentprojection",
        "native:importintopostgis",
        "native:importintospatialite",
        "native:importintospatialiteregistered",
        "native:postgisexecutesql",
        "native:postgisexecuteandloadsql",
        "native:spatialiteexecutesql",
        "native:spatialiteexecutesqlregistered",
        "qgis:truncatetable",
        "qgis:zonalstatistics",
        "qgis:importintopostgis",
        "qgis:importintospatialite",
        "gdal:assignprojection",
        "gdal:overviews",
        "gdal:rasterize_over",
        "gdal:rasterize_over_fixed_value",
        "gdal:importvectorintopostgisdatabaseavailableconnections",
        "gdal:importvectorintopostgisdatabasenewconnection",
    }
)

# The senders can push arbitrary data out (POST bodies): each call needs its own confirmation.
NETWORK_SENDERS = frozenset({"native:filedownloader", "native:httprequest"})
NETWORK_ALGORITHMS = NETWORK_SENDERS | frozenset({"native:batchnominatimgeocoder", "native:downloadvectortiles"})


def contacts_network(identifier: str) -> bool:
    return identifier.strip().lower() in NETWORK_ALGORITHMS


def sends_network_data(identifier: str) -> bool:
    return identifier.strip().lower() in NETWORK_SENDERS


def writes_external_data(identifier: str, security_risk: bool = False) -> bool:
    normalized = identifier.strip().lower()
    if not normalized:
        return security_risk
    provider = normalized.partition(":")[0]
    return security_risk or normalized in SOURCE_WRITERS or provider not in BUILTIN_PROVIDERS
