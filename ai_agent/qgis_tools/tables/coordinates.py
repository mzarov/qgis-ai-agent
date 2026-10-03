"""Which columns of a delimited table hold coordinates, and in which CRS.

Pure Python: the guess serves the preview and the attach button, the checks
run in `prepare` so a points layer is never built from swapped or projected
numbers labelled as degrees.
"""

import re
from dataclasses import dataclass

from ai_agent.qgis_tools.tables.delimited import DelimitedTable

WGS84 = "EPSG:4326"
X_NAMES = frozenset({"lon", "lng", "long", "longitude", "x", "xcoord", "coordx", "pointx", "easting", "east"})
Y_NAMES = frozenset({"lat", "latitude", "y", "ycoord", "coordy", "pointy", "northing", "north"})
WKT_NAMES = frozenset({"wkt", "geom", "geometry", "thegeom", "shape", "wktgeom"})
# The dimension tag may be glued on (POINTZ) or apart (POINT Z); either way
# the geometry opens a bracket or is EMPTY.
WKT_PREFIX = re.compile(
    r"\s*(SRID=\d+;\s*)?(MULTI)?(POINT|LINESTRING|POLYGON|CURVEPOLYGON|GEOMETRYCOLLECTION)\s*(ZM|Z|M)?\s*(?=\(|EMPTY)",
    re.IGNORECASE,
)
WKT_SEPARATORS = re.compile(r"[(),]")
WKT_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
MAX_LONGITUDE = 180.0
MAX_LATITUDE = 90.0
SHOWN_BAD_VALUES = 3


@dataclass(frozen=True)
class Coordinates:
    x_field: str = ""
    y_field: str = ""
    wkt_field: str = ""
    crs: str = ""

    @property
    def found(self) -> bool:
        return bool(self.wkt_field or (self.x_field and self.y_field))


def guess_coordinates(table: DelimitedTable) -> Coordinates:
    """Coordinate columns recognised by name and confirmed by the values; CRS only when they fit degrees."""
    by_name = {_plain(column): column for column in table.header}
    x_field = next((by_name[name] for name in by_name if name in X_NAMES), "")
    y_field = next((by_name[name] for name in by_name if name in Y_NAMES), "")
    if x_field and y_field:
        xs, ys = _numbers(table, x_field), _numbers(table, y_field)
        if xs is not None and ys is not None and xs and ys:
            return Coordinates(x_field=x_field, y_field=y_field, crs=WGS84 if fits_degrees(xs, ys) else "")
    for column in table.header:
        values = table.values(column)
        if values and (_plain(column) in WKT_NAMES or WKT_PREFIX.match(values[0])) and _all_wkt(values):
            xs, ys = wkt_pairs(values)
            return Coordinates(wkt_field=column, crs=WGS84 if xs and fits_degrees(xs, ys) else "")
    return Coordinates()


def checked_xy_crs(table: DelimitedTable, x_field: str, y_field: str, crs: str, geographic: bool = False) -> str:
    """The CRS for an x/y points layer; raises when the numbers cannot be what is claimed.

    `crs` is a normalised authority id or empty; `geographic` says whether it is in degrees.
    """
    table.require_columns([x_field, y_field])
    xs = _require_numbers(table, x_field)
    ys = _require_numbers(table, y_field)
    return _checked_crs(xs, ys, crs, geographic, f"columns '{x_field}'/'{y_field}'")


def checked_wkt_crs(table: DelimitedTable, wkt_field: str, crs: str, geographic: bool = False) -> str:
    table.require_columns([wkt_field])
    values = table.values(wkt_field)
    bad = [value for value in values if not WKT_PREFIX.match(value)]
    if not values or bad:
        shown = ", ".join(repr(value[:40]) for value in bad[:SHOWN_BAD_VALUES]) or "no values"
        raise ValueError(f"Column '{wkt_field}' does not hold WKT geometries ({shown}).")
    xs, ys = wkt_pairs(values)
    return _checked_crs(xs, ys, crs, geographic, f"the WKT in '{wkt_field}'")


def fits_degrees(xs: list[float], ys: list[float]) -> bool:
    return all(abs(x) <= MAX_LONGITUDE for x in xs) and all(abs(y) <= MAX_LATITUDE for y in ys)


def wkt_pairs(values: list[str]) -> tuple[list[float], list[float]]:
    """x and y of every vertex: the first two numbers of each coordinate tuple, whatever Z or M follows."""
    xs: list[float] = []
    ys: list[float] = []
    for value in values:
        body = WKT_PREFIX.sub("", value, count=1)
        for vertex in WKT_SEPARATORS.split(body):
            numbers = WKT_NUMBER.findall(vertex)
            if len(numbers) >= 2:
                xs.append(float(numbers[0]))
                ys.append(float(numbers[1]))
    return xs, ys


def _checked_crs(xs: list[float], ys: list[float], crs: str, geographic: bool, where: str) -> str:
    wanted = crs.strip()
    if xs and ys and _swapped(xs, ys) and (not wanted or geographic):
        raise ValueError(
            f"The values of {where} look swapped: the x values fit latitude and the y values only fit "
            "longitude. Pass the longitude column as x_field and the latitude column as y_field."
        )
    if wanted:
        if geographic and xs and not fits_degrees(xs, ys):
            raise ValueError(
                f"The values of {where} (e.g. {xs[0]:g}, {ys[0]:g}) are outside longitude/latitude, so they "
                f"are not {wanted}. Pass the projected CRS they were written in."
            )
        return wanted
    if xs and fits_degrees(xs, ys):
        return WGS84
    sample = f" (e.g. {xs[0]:g}, {ys[0]:g})" if xs and ys else ""
    raise ValueError(
        f"The values of {where}{sample} are not longitude/latitude degrees. Pass crs: the projected "
        "system they were written in, such as a UTM zone or a national grid."
    )


def _swapped(xs: list[float], ys: list[float]) -> bool:
    return all(abs(x) <= MAX_LATITUDE for x in xs) and any(MAX_LATITUDE < abs(y) <= MAX_LONGITUDE for y in ys)


def _require_numbers(table: DelimitedTable, column: str) -> list[float]:
    numbers = _numbers(table, column)
    if numbers is None:
        bad = [value for value in table.values(column) if table.number(value) is None]
        shown = ", ".join(repr(value) for value in bad[:SHOWN_BAD_VALUES])
        raise ValueError(f"Column '{column}' is not numeric ({shown}); coordinates must be plain numbers.")
    if not numbers:
        raise ValueError(f"Column '{column}' is empty in the first rows; it cannot hold coordinates.")
    return numbers


def _numbers(table: DelimitedTable, column: str) -> list[float] | None:
    parsed = [table.number(value) for value in table.values(column)]
    numbers = [number for number in parsed if number is not None]
    return numbers if len(numbers) == len(parsed) else None


def _all_wkt(values: list[str]) -> bool:
    return all(WKT_PREFIX.match(value) for value in values)


def _plain(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())
