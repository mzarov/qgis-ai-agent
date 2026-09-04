BUILTIN_PROVIDERS = frozenset({"native", "qgis", "gdal"})

# Processing has no general "modifies its input" flag. These algorithms write
# through their input/provider parameters, outside the declared output paths.
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


def writes_external_data(identifier: str, security_risk: bool = False) -> bool:
    """Classify source writes separately from output destinations.

    Scripts, models and third-party providers can perform arbitrary effects;
    their parameter schemas are not a guarantee of reversibility. Built-in
    additions that mutate inputs must be reviewed against SOURCE_WRITERS.
    """
    normalized = identifier.strip().lower()
    if not normalized:
        return security_risk
    provider = normalized.partition(":")[0]
    return security_risk or normalized in SOURCE_WRITERS or provider not in BUILTIN_PROVIDERS
