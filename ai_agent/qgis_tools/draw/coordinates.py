"""Coordinates typed by the model: parsing, sanity checks, CRS and geometry building."""

import math
from typing import Any

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

WGS84 = "EPSG:4326"
UTM_KEYWORD = "utm"
POINT = "point"
LINE = "line"
POLYGON = "polygon"
GEOMETRIES = (POINT, LINE, POLYGON)
MIN_VERTICES = {POINT: 1, LINE: 2, POLYGON: 3}
MAX_FEATURES = 1000
MAX_VERTICES = 10000
MAX_LONGITUDE = 180.0
MAX_LATITUDE = 90.0
# UTM zones stop at these latitudes; beyond them a polar CRS is needed.
UTM_LATITUDE_LIMIT = 84.0
UTM_NORTH_BASE = 32600
UTM_SOUTH_BASE = 32700

Vertex = tuple[float, float]


def checked_geometry(raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in GEOMETRIES:
        raise ValueError(f"Unknown geometry '{raw}'. Available: {', '.join(GEOMETRIES)}.")
    return kind


def checked_crs(raw: Any, parameter: str = "crs") -> QgsCoordinateReferenceSystem:
    text = str(raw or "").strip() or WGS84
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        raise ValueError(f"Unknown CRS '{text}' in {parameter}. Give an authority id such as {WGS84} or EPSG:32637.")
    return crs


def crs_label(crs: QgsCoordinateReferenceSystem, fallback: Any) -> str:
    authid = crs.authid()
    return authid if isinstance(authid, str) and authid else str(fallback or WGS84).strip()


def parse_vertices(raw: Any, geometry: str, position: int) -> list[Vertex]:
    """The `coordinates` of feature number `position` as (x, y) pairs.

    A point also accepts a bare [x, y] pair; every geometry accepts a list of pairs.
    """
    where = f"features[{position}].coordinates"
    if geometry == POINT and _is_pair(raw):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{where} must be a list of [x, y] pairs, e.g. [[37.62, 55.75]].")
    if len(raw) > MAX_VERTICES:
        raise ValueError(f"{where} has {len(raw)} vertices; at most {MAX_VERTICES} per feature.")
    vertices = [_vertex(item, where, index) for index, item in enumerate(raw)]
    _check_vertex_count(vertices, geometry, where)
    return vertices


def check_ranges(
    shapes: list[list[Vertex]], crs: QgsCoordinateReferenceSystem, crs_text: str, small_values_confirmed: bool = False
) -> None:
    """Refuse coordinates that cannot be in `crs`: swapped lat/lon, or degrees in a metric CRS.

    Genuine small projected values (a local grid, EPSG:3857 near 0,0) pass once
    `small_values_confirmed` says the caller has independent evidence for them.
    """
    pairs = [vertex for vertices in shapes for vertex in vertices]
    if not pairs:
        return
    if crs.isGeographic():
        for x, y in pairs:
            if abs(x) <= MAX_LONGITUDE and abs(y) <= MAX_LATITUDE:
                continue
            if abs(y) <= MAX_LONGITUDE and abs(x) <= MAX_LATITUDE:
                raise ValueError(
                    f"[{x}, {y}] has a latitude beyond ±90: the pair looks swapped. "
                    f"Coordinates are [longitude, latitude] — pass [{y}, {x}]."
                )
            raise ValueError(
                f"[{x}, {y}] is outside the range of {crs_text} (longitude ±180, latitude ±90). "
                "If these are projected metres, set crs to their CRS."
            )
        return
    if not small_values_confirmed and all(abs(x) <= MAX_LONGITUDE and abs(y) <= MAX_LATITUDE for x, y in pairs):
        raise ValueError(
            f"Every coordinate is within ±180/±90, which looks like longitude/latitude in degrees, "
            f"but crs is {crs_text}, measured in metres or feet. For lon/lat pass crs {WGS84}. "
            "If they really are small projected values (a local grid, EPSG:3857 near 0,0), confirm it: "
            f"for a new layer also set layer_crs to {crs_text}; an existing layer in {crs_text} accepts "
            "them when they fall inside its extent."
        )


def check_polygon_ring(vertices: list[Vertex], position: int) -> None:
    geometry = build_geometry(POLYGON, [QgsPointXY(x, y) for x, y in vertices])
    if not geometry.isGeosValid():
        raise ValueError(
            f"features[{position}] is not a valid polygon: its ring crosses itself or collapses. "
            "List the vertices in order around the boundary."
        )


def build_geometry(geometry: str, points: list[Any]) -> QgsGeometry:
    if geometry == POINT:
        return QgsGeometry.fromPointXY(points[0])
    if geometry == LINE:
        return QgsGeometry.fromPolylineXY(points)
    return QgsGeometry.fromPolygonXY([points])


def transformed_points(
    vertices: list[Vertex], source: QgsCoordinateReferenceSystem, target: QgsCoordinateReferenceSystem
) -> list[Any]:
    points = [QgsPointXY(x, y) for x, y in vertices]
    if not target.isValid() or source.authid() == target.authid():
        return points
    transform = QgsCoordinateTransform(source, target, QgsProject.instance())
    try:
        return [transform.transform(point) for point in points]
    except Exception as failure:
        raise ValueError(
            f"Could not move the coordinates from {source.authid()} into {target.authid()}: {failure}. "
            "Check that they really are in the given crs."
        ) from None


def utm_crs_for(shapes: list[list[Vertex]], source: QgsCoordinateReferenceSystem) -> QgsCoordinateReferenceSystem:
    """The UTM zone around the middle of the coordinates."""
    pairs = [vertex for vertices in shapes for vertex in vertices]
    if not pairs:
        raise ValueError("layer_crs 'utm' needs coordinates to pick the zone from; give an explicit CRS instead.")
    middle = (sum(x for x, _ in pairs) / len(pairs), sum(y for _, y in pairs) / len(pairs))
    longitude, latitude = transformed_lonlat(middle, source)
    if abs(latitude) > UTM_LATITUDE_LIMIT:
        raise ValueError(
            f"UTM does not cover latitude {latitude:.1f}. Give a polar layer_crs such as EPSG:3413 or EPSG:3031."
        )
    zone = max(1, min(60, int((longitude + MAX_LONGITUDE) / 6.0) + 1))
    base = UTM_NORTH_BASE if latitude >= 0 else UTM_SOUTH_BASE
    return checked_crs(f"EPSG:{base + zone}", "layer_crs")


def transformed_lonlat(vertex: Vertex, source: QgsCoordinateReferenceSystem) -> Vertex:
    wgs84 = checked_crs(WGS84)
    point = transformed_points([vertex], source, wgs84)[0]
    return float(point.x()), float(point.y())


def _vertex(item: Any, where: str, index: int) -> Vertex:
    if not _is_pair(item):
        raise ValueError(f"{where}[{index}] must be an [x, y] pair of numbers, got {item!r}.")
    x, y = float(item[0]), float(item[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"{where}[{index}] is not a finite pair of numbers.")
    return x, y


def _is_pair(item: Any) -> bool:
    if not isinstance(item, (list, tuple)) or len(item) != 2:
        return False
    return all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in item)


def _check_vertex_count(vertices: list[Vertex], geometry: str, where: str) -> None:
    if geometry == POINT and len(vertices) != 1:
        raise ValueError(f"{where} holds {len(vertices)} pairs; a point feature has exactly one [x, y].")
    distinct = list(dict.fromkeys(vertices))
    needed = MIN_VERTICES[geometry]
    if len(distinct) < needed:
        raise ValueError(f"{where} needs at least {needed} distinct vertices for a {geometry}, got {len(distinct)}.")
