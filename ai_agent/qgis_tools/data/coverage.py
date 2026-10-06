"""How much of the searched rectangle a scene's footprint covers, in plain Python.

A Sentinel-2 tile at the edge of a satellite swath holds data in a sliver only;
"clearest" alone picked such a tile for a city it barely touched. Footprints
are lon/lat polygons, small enough that planar area is a fair share measure.
"""

from typing import Any

Point = tuple[float, float]
FULL_COVER = 95.0


def covered_share(footprint: Any, bbox: tuple[float, float, float, float]) -> float | None:
    """Percent of `bbox` inside the GeoJSON `footprint` (Polygon or MultiPolygon); None when unreadable."""
    rings = _outer_rings(footprint)
    if rings is None:
        return None
    west, south, east, north = bbox
    total = (east - west) * (north - south)
    if total <= 0:
        return None
    inside = sum(abs(_area(_clip(ring, bbox))) for ring in rings)
    return round(min(100.0, 100.0 * inside / total), 1)


def _outer_rings(geometry: Any) -> list[list[Point]] | None:
    if not isinstance(geometry, dict):
        return None
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    try:
        if kind == "Polygon":
            return [[(float(x), float(y)) for x, y, *_ in coordinates[0]]]
        if kind == "MultiPolygon":
            return [[(float(x), float(y)) for x, y, *_ in polygon[0]] for polygon in coordinates]
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _clip(ring: list[Point], bbox: tuple[float, float, float, float]) -> list[Point]:
    """Sutherland–Hodgman: the part of the ring inside the rectangle."""
    west, south, east, north = bbox
    edges = (
        (lambda p: p[0] >= west, lambda a, b: _at_x(a, b, west)),
        (lambda p: p[0] <= east, lambda a, b: _at_x(a, b, east)),
        (lambda p: p[1] >= south, lambda a, b: _at_y(a, b, south)),
        (lambda p: p[1] <= north, lambda a, b: _at_y(a, b, north)),
    )
    points = ring
    for inside, cross in edges:
        if not points:
            break
        clipped: list[Point] = []
        previous = points[-1]
        for point in points:
            if inside(point):
                if not inside(previous):
                    clipped.append(cross(previous, point))
                clipped.append(point)
            elif inside(previous):
                clipped.append(cross(previous, point))
            previous = point
        points = clipped
    return points


def _at_x(a: Point, b: Point, x: float) -> Point:
    t = (x - a[0]) / ((b[0] - a[0]) or 1e-12)
    return x, a[1] + t * (b[1] - a[1])


def _at_y(a: Point, b: Point, y: float) -> Point:
    t = (y - a[1]) / ((b[1] - a[1]) or 1e-12)
    return a[0] + t * (b[0] - a[0]), y


def _area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1], strict=False)) / 2
