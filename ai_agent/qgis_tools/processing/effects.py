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
        "native:setlayermetadata",
        "native:copylayermetadata",
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

# Effects no output check sees: another application, a GPS device, atlas files named by an expression.
UNCHECKED_WRITERS = frozenset(
    {"native:openurl", "native:uploadgpsdata", "native:atlaslayouttoimage", "native:atlaslayouttomultiplepdf"}
)

# A new folder replaces nothing, but Undo leaves it behind.
FOLDER_CREATORS = frozenset({"native:createdirectory"})

# Their SQL reaches every QGIS and GDAL function, including ones that write files or geocode online.
SQL_RUNNERS = frozenset({"qgis:executesql", "gdal:executesql"})

# The senders push data out (POST bodies, uploaded files, geocoded addresses): each call needs its own confirmation.
NETWORK_SENDERS = frozenset(
    {"native:filedownloader", "native:httprequest", "native:fileuploader", "native:batchnominatimgeocoder"}
)
NETWORK_ALGORITHMS = NETWORK_SENDERS | frozenset({"native:downloadvectortiles"})


def contacts_network(identifier: str) -> bool:
    return _normalized(identifier) in NETWORK_ALGORITHMS


def needs_own_confirmation(identifier: str) -> bool:
    normalized = _normalized(identifier)
    return normalized in NETWORK_SENDERS or normalized in SQL_RUNNERS


def creates_folders(identifier: str) -> bool:
    return _normalized(identifier) in FOLDER_CREATORS


def writes_external_data(identifier: str, security_risk: bool = False) -> bool:
    normalized = _normalized(identifier)
    if not normalized:
        return security_risk
    provider = normalized.partition(":")[0]
    return (
        security_risk
        or normalized in SOURCE_WRITERS
        or normalized in UNCHECKED_WRITERS
        or provider not in BUILTIN_PROVIDERS
    )


def _normalized(identifier: str) -> str:
    return identifier.strip().lower()
