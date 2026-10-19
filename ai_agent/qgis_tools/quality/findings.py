from collections.abc import Iterable, Mapping
from typing import Any

from ai_agent.qgis_tools.quality.tally import Bounds, Tally

PROBLEM_INVALID = "invalid_geometry"
PROBLEM_EMPTY = "empty_geometry"
PROBLEM_DUPLICATE = "duplicate_geometry"
PROBLEM_EMPTY_FIELDS = "empty_fields"
PROBLEM_COORDINATES = "suspicious_coordinates"
PROBLEM_CRS = "invalid_crs"
PROBLEM_EXTENT = "empty_extent"
PROBLEM_ORDER = (
    PROBLEM_CRS,
    PROBLEM_COORDINATES,
    PROBLEM_EXTENT,
    PROBLEM_INVALID,
    PROBLEM_EMPTY,
    PROBLEM_DUPLICATE,
    PROBLEM_EMPTY_FIELDS,
)
COORDINATES_PROJECTED = "projected"
COORDINATES_DEGREES = "degrees"
MAX_DEGREES_X = 180.0
MAX_DEGREES_Y = 90.0
MAX_LISTED_FIELDS = 20
MANY_CRS = 3
MAX_LISTED_CRS = 6
COORD_DIGITS = 6

SUGGESTIONS = {
    PROBLEM_CRS: (
        "No valid CRS: native:assignprojection (processing skill) writes a copy with the CRS the data were "
        "made in; ask the user which one when the source does not say."
    ),
    PROBLEM_EXTENT: (
        "Empty extent: the raster source is probably broken or unreadable; tell the user, do not process it."
    ),
    PROBLEM_INVALID: (
        "Invalid geometries: native:fixgeometries (processing skill) repairs them into a new layer; "
        "the source stays as it is."
    ),
    PROBLEM_EMPTY: (
        "Features without geometry: native:removenullgeometries (processing skill; REMOVE_EMPTY true drops "
        "empty ones too) writes a new layer without them."
    ),
    PROBLEM_DUPLICATE: (
        "Repeated geometries: native:deleteduplicategeometries (processing skill) keeps one feature of each "
        "in a new layer; their attributes may differ, so show the user the sample ids first."
    ),
    PROBLEM_EMPTY_FIELDS: (
        "Fields with no values: delete_field (fields skill) removes one, only if the user wants it gone."
    ),
}
COORDINATE_SUGGESTIONS = {
    COORDINATES_PROJECTED: (
        "Coordinates outside ±180/±90 under a geographic CRS: the numbers are most likely projected and the "
        "layer's CRS is wrong. Find out which CRS they are in (ask the user when unsure), then "
        "native:assignprojection (processing skill) writes a copy with that CRS. Do not reproject: "
        "native:reprojectlayer would transform the wrong numbers."
    ),
    COORDINATES_DEGREES: (
        "Every coordinate fits within ±180/±90 under a projected CRS: the numbers look like degrees. If they are, "
        "native:assignprojection with EPSG:4326 (processing skill) writes a copy with the right CRS; "
        "reprojecting would not fix it."
    ),
}
PROJECT_CRS_SUGGESTION = (
    "Layers in several CRSs: QGIS draws them together, but an overlay of two layers is safest with both in "
    "one projected CRS; native:reprojectlayer (processing skill) writes reprojected copies."
)
NODATA_SUGGESTION = (
    "No nodata value: if a value such as 0 or -9999 marks missing cells, set_raster_style with no_data_values "
    "(style skill) hides it on the map, and gdal:translate with NODATA (processing skill) writes a copy that "
    "declares it."
)
COORDINATE_NOTES = {
    COORDINATES_PROJECTED: (
        "The layer CRS is geographic, yet coordinates fall outside ±180/±90 (see data_bounds): they are "
        "probably projected numbers under a wrong CRS."
    ),
    COORDINATES_DEGREES: (
        "The layer CRS is projected, yet every coordinate fits within ±180/±90 (see data_bounds): the numbers "
        "look like degrees under a wrong CRS, unless the data really lie within a few hundred units of the origin."
    ),
}


def coordinate_kind(geographic: bool, bounds: Bounds | None) -> str:
    if bounds is None:
        return ""
    in_degrees = (
        max(abs(bounds.xmin), abs(bounds.xmax)) <= MAX_DEGREES_X
        and max(abs(bounds.ymin), abs(bounds.ymax)) <= MAX_DEGREES_Y
    )
    if geographic and not in_degrees:
        return COORDINATES_PROJECTED
    if not geographic and in_degrees:
        return COORDINATES_DEGREES
    return ""


def bounds_dict(bounds: Bounds) -> dict[str, float]:
    return {
        "xmin": round(bounds.xmin, COORD_DIGITS),
        "ymin": round(bounds.ymin, COORD_DIGITS),
        "xmax": round(bounds.xmax, COORD_DIGITS),
        "ymax": round(bounds.ymax, COORD_DIGITS),
    }


def coordinate_block(geographic: bool, bounds: Bounds | None) -> dict[str, Any]:
    kind = coordinate_kind(geographic, bounds)
    if not kind or bounds is None:
        return {}
    return {"coordinates": COORDINATE_NOTES[kind], "data_bounds": bounds_dict(bounds)}


def crs_spread(labels: Iterable[str]) -> str:
    distinct = list(dict.fromkeys(label for label in labels if label))
    if len(distinct) < MANY_CRS:
        return ""
    shown = ", ".join(distinct[:MAX_LISTED_CRS])
    more = f" and {len(distinct) - MAX_LISTED_CRS} more" if len(distinct) > MAX_LISTED_CRS else ""
    return f"The project's data layers use {len(distinct)} different CRSs: {shown}{more}."


def ordered_problems(counts: Mapping[str, int]) -> dict[str, int]:
    return {name: int(counts[name]) for name in PROBLEM_ORDER if int(counts.get(name) or 0) > 0}


def vector_findings(tally: Tally, geographic: bool, crs_valid: bool) -> dict[str, Any]:
    empty_fields = tally.empty_fields()
    coordinates = coordinate_block(geographic, tally.bounds) if crs_valid else {}
    problems = ordered_problems(
        {
            PROBLEM_CRS: 0 if crs_valid else 1,
            PROBLEM_COORDINATES: 1 if coordinates else 0,
            PROBLEM_INVALID: tally.invalid,
            PROBLEM_EMPTY: tally.empty,
            PROBLEM_DUPLICATE: tally.duplicates,
            PROBLEM_EMPTY_FIELDS: len(empty_fields),
        }
    )
    report: dict[str, Any] = {"problems": problems}
    gaps = tally.partly_missing()
    if gaps:
        report["missing_values"] = {
            name: {key: count for key, count in (("null", gap.null), ("blank", gap.blank)) if count}
            for name, gap in gaps[:MAX_LISTED_FIELDS]
        }
    if tally.invalid_samples:
        report["invalid_geometry"] = [{"id": fid, "reason": reason} for fid, reason in tally.invalid_samples]
    if tally.empty_ids:
        report["empty_geometry_ids"] = list(tally.empty_ids)
    if tally.group_samples:
        report["duplicate_geometry_groups"] = [list(ids) for ids in tally.group_samples.values()]
        if tally.duplicate_groups > len(tally.group_samples):
            report["duplicate_groups_total"] = tally.duplicate_groups
    if empty_fields:
        report["empty_fields"] = empty_fields[:MAX_LISTED_FIELDS]
    report.update(coordinates)
    return report


def suggestions(
    problems: Mapping[str, int],
    coordinates: str = "",
    crs_spread_found: bool = False,
    nodata_missing: bool = False,
) -> list[str]:
    found: list[str] = []
    for name in PROBLEM_ORDER:
        if not problems.get(name):
            continue
        if name == PROBLEM_COORDINATES:
            text = COORDINATE_SUGGESTIONS.get(coordinates, "")
        else:
            text = SUGGESTIONS.get(name, "")
        if text:
            found.append(text)
    if nodata_missing:
        found.append(NODATA_SUGGESTION)
    if crs_spread_found:
        found.append(PROJECT_CRS_SUGGESTION)
    return found
