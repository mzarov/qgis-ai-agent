import math
from contextlib import suppress
from typing import Any

from qgis.core import QgsRasterLayer

from ai_agent.qgis_tools.quality.findings import (
    PROBLEM_COORDINATES,
    PROBLEM_CRS,
    PROBLEM_EXTENT,
    coordinate_block,
    coordinate_kind,
    ordered_problems,
)
from ai_agent.qgis_tools.quality.tally import Bounds

MAX_RASTER_BANDS = 20
FILE_PROVIDER = "gdal"
NAN_TEXT = "NaN"
NODATA_NOTE = (
    "No band declares a nodata value: if a value such as 0 or -9999 marks missing cells, it is drawn and counted "
    "as data."
)


def raster_findings(layer: QgsRasterLayer, geographic: bool, crs_valid: bool) -> tuple[dict[str, Any], str]:
    band_count = _band_count(layer)
    bounds = _extent(layer)
    coordinates = coordinate_block(geographic, bounds) if crs_valid else {}
    report: dict[str, Any] = {
        "band_count": band_count,
        "problems": ordered_problems(
            {
                PROBLEM_CRS: 0 if crs_valid else 1,
                PROBLEM_EXTENT: 1 if bounds is None else 0,
                PROBLEM_COORDINATES: 1 if coordinates else 0,
            }
        ),
    }
    nodata = [_nodata(layer, band) for band in range(1, min(band_count, MAX_RASTER_BANDS) + 1)]
    report["nodata_by_band"] = nodata
    if band_count > MAX_RASTER_BANDS:
        report["bands_note"] = f"nodata is listed for the first {MAX_RASTER_BANDS} bands of {band_count}"
    if nodata and all(value is None for value in nodata) and _is_file(layer):
        report["nodata_note"] = NODATA_NOTE
    report.update(coordinates)
    return report, coordinate_kind(geographic, bounds) if crs_valid else ""


def _band_count(layer: QgsRasterLayer) -> int:
    try:
        return max(0, int(layer.bandCount()))
    except Exception:
        return 0


def _extent(layer: QgsRasterLayer) -> Bounds | None:
    try:
        extent = layer.extent()
        if extent.isNull() or extent.isEmpty():
            return None
        return Bounds(extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    except Exception:
        return None


def _nodata(layer: QgsRasterLayer, band: int) -> float | str | None:
    with suppress(Exception):
        provider = layer.dataProvider()
        if provider.sourceHasNoDataValue(band) and provider.useSourceNoDataValue(band):
            return _plain(float(provider.sourceNoDataValue(band)))
        ranges = list(provider.userNoDataValues(band))
        if ranges:
            return _plain(float(ranges[0].min()))
    return None


def _plain(value: float) -> float | str:
    return NAN_TEXT if math.isnan(value) else value


def _is_file(layer: QgsRasterLayer) -> bool:
    try:
        return str(layer.providerType() or "").lower() == FILE_PROVIDER
    except Exception:
        return False
