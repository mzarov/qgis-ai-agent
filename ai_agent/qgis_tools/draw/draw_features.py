from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import bind_layer_reference
from ai_agent.qgis_tools.draw.attributes import (
    FIELD_TYPES,
    check_existing_fields,
    checked_attributes,
    coerced_rows,
    new_layer_schema,
)
from ai_agent.qgis_tools.draw.coordinates import (
    GEOMETRIES,
    LINE,
    MAX_FEATURES,
    POINT,
    POLYGON,
    UTM_KEYWORD,
    WGS84,
    Vertex,
    check_polygon_ring,
    check_ranges,
    checked_crs,
    checked_geometry,
    crs_label,
    parse_vertices,
    transformed_points,
)
from ai_agent.qgis_tools.draw.targets import (
    append_to_layer,
    check_existing_target,
    check_free_name,
    draw_new_layer,
    existing_layer,
    is_memory,
    new_layer_crs,
)

NEW_LAYER_ONLY = ("layer_crs", "fields")


class DrawFeaturesTool(BaseTool):
    name = "draw_features"
    description = (
        "Create features from coordinates: points, a line through points, or a polygon ring. "
        "Either into a new scratch (memory) layer — new_layer_name — or appended to an existing "
        "vector layer of the same geometry — layer_name."
    )
    skill = "draw"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    # Appending to a file or database layer commits to its source: see has_external_effect.
    external_effect = False
    network_access = False
    constraints = [
        f"Coordinates are [x, y] = [longitude, latitude] in {WGS84} unless crs says otherwise",
        "Exactly one of layer_name and new_layer_name",
        f"At most {MAX_FEATURES} features per call",
    ]
    examples = ["Put a point at 55.75, 37.62", "Draw a line between these two towns"]
    params_schema = [
        {
            "name": "new_layer_name",
            "type": "string",
            "description": "Create a new scratch layer with this name and draw into it",
            "required": False,
        },
        {
            "name": "layer_name",
            "type": "string",
            "description": "Existing layer to append to, exactly as in the project",
            "required": False,
        },
        {
            "name": "layer_id",
            "type": "string",
            "description": "Stable id of the existing layer; required when names are duplicated",
            "required": False,
        },
        {"name": "geometry", "type": "string", "enum": list(GEOMETRIES), "description": "Feature kind"},
        {
            "name": "features",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "coordinates": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                    "attributes": {"type": "object"},
                },
            },
            "description": (
                'One object per feature: {"coordinates": [[x, y], ...], "attributes": {"name": "..."}}. '
                "A point has one pair, a line two or more, a polygon its ring of three or more (closed automatically)"
            ),
        },
        {
            "name": "crs",
            "type": "string",
            "description": f"CRS of the coordinates, default {WGS84}",
            "required": False,
        },
        {
            "name": "layer_crs",
            "type": "string",
            "description": (
                f"New layer only: its CRS, default the coordinates' crs. '{UTM_KEYWORD}' picks the local "
                "UTM zone — metres for a later buffer"
            ),
            "required": False,
        },
        {
            "name": "fields",
            "type": "object",
            "description": (
                f"New layer only: field name → type ({', '.join(FIELD_TYPES)}). "
                "Attribute names not listed get a type from their values"
            ),
            "required": False,
        },
    ]

    def safety_for(self, params: dict[str, Any]) -> str:
        return SAFETY_DESTRUCTIVE if self.has_external_effect(params) else SAFETY_WRITE

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        """A file or database layer is committed to its source, which a project snapshot cannot restore."""
        if _new_name(params):
            return False
        try:
            return not is_memory(existing_layer(params))
        except Exception:
            return True

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        geometry = checked_geometry(params.get("geometry"))
        new_name = _new_name(params)
        _check_target_choice(params, new_name)
        source = checked_crs(params.get("crs"))
        shapes, rows = _parsed_features(params.get("features"), geometry, allow_empty=bool(new_name))
        crs_text = crs_label(source, params.get("crs"))
        check_ranges(shapes, source, crs_text)
        vertices = [vertex for shape in shapes for vertex in shape]
        prepared = {key: value for key, value in params.items() if key not in NEW_LAYER_ONLY and value is not None}
        prepared.update(geometry=geometry, crs=crs_text)
        if new_name:
            check_free_name(new_name)
            schema = new_layer_schema(params.get("fields"), rows)
            target = new_layer_crs(params.get("layer_crs"), source, shapes)
            transformed_points(vertices, source, target)
            prepared.update(
                new_layer_name=new_name,
                layer_crs=crs_label(target, params.get("layer_crs")),
                fields=schema,
                features=_normalized(shapes, coerced_rows(schema, rows)),
            )
            return prepared
        layer = existing_layer(params)
        check_existing_target(layer, geometry)
        check_existing_fields(layer, rows)
        transformed_points(vertices, source, layer.crs())
        prepared["features"] = _normalized(shapes, rows)
        return bind_layer_reference(prepared, layer)

    def summarize_call(self, params: dict[str, Any]) -> str:
        features = params.get("features")
        count = len(features) if isinstance(features, list) else 0
        kind = str(params.get("geometry") or "").strip().lower()
        new_name = _new_name(params)
        if new_name:
            return _new_layer_summary(kind).format(count, new_name)
        return _append_summary(kind).format(count, str(params.get("layer_name") or "").strip())

    def detail_call(self, params: dict[str, Any]) -> str:
        features = params.get("features")
        count = len(features) if isinstance(features, list) else 0
        return "\n".join(
            [
                tr("Layer: {0}").format(str(params.get("layer_name") or "").strip()),
                tr("Features to add: {0}").format(count),
                tr("They are committed to the layer's data source; Undo does not remove them."),
            ]
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        geometry = checked_geometry(params.get("geometry"))
        new_name = _new_name(params)
        source = checked_crs(params.get("crs"))
        shapes, rows = _parsed_features(params.get("features"), geometry, allow_empty=bool(new_name))
        if new_name:
            schema = new_layer_schema(params.get("fields"), rows)
            target = new_layer_crs(params.get("layer_crs"), source, shapes)
            return draw_new_layer(new_name, geometry, source, target, shapes, rows, schema)
        return append_to_layer(existing_layer(params), geometry, source, shapes, rows)


def _parsed_features(raw: Any, geometry: str, allow_empty: bool) -> tuple[list[list[Vertex]], list[dict[str, Any]]]:
    if not isinstance(raw, list) or (not raw and not allow_empty):
        raise ValueError('features must be a non-empty list of {"coordinates": [[x, y], ...]} objects.')
    if len(raw) > MAX_FEATURES:
        raise ValueError(f"{len(raw)} features in one call; at most {MAX_FEATURES}. Split the work.")
    shapes, rows = [], []
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f'features[{position}] must be an object: {{"coordinates": [[x, y]], "attributes": {{}}}}.'
            )
        vertices = parse_vertices(item.get("coordinates"), geometry, position)
        if geometry == POLYGON:
            check_polygon_ring(vertices, position)
        shapes.append(vertices)
        rows.append(checked_attributes(item.get("attributes"), position))
    return shapes, rows


def _normalized(shapes: list[list[Vertex]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for vertices, row in zip(shapes, rows, strict=False):
        item: dict[str, Any] = {"coordinates": [[x, y] for x, y in vertices]}
        if row:
            item["attributes"] = row
        normalized.append(item)
    return normalized


def _new_name(params: Any) -> str:
    raw = params.get("new_layer_name") if isinstance(params, dict) else None
    return raw.strip() if isinstance(raw, str) else ""


def _check_target_choice(params: dict[str, Any], new_name: str) -> None:
    existing = str(params.get("layer_name") or "").strip() or str(params.get("layer_id") or "").strip()
    if new_name and existing:
        raise ValueError(
            "Give either new_layer_name (create a scratch layer) or layer_name (append to an existing one), not both."
        )
    if not new_name and not existing:
        raise ValueError("Say where to draw: new_layer_name for a new scratch layer, or layer_name of an existing one.")
    if not new_name and any(params.get(key) for key in NEW_LAYER_ONLY):
        raise ValueError(
            "layer_crs and fields describe a new layer only. An existing layer keeps its CRS and fields; "
            "the coordinates are transformed into its CRS."
        )


def _new_layer_summary(kind: str) -> str:
    if kind == POINT:
        return tr("Drawing {0} point(s) in new scratch layer '{1}'.")
    if kind == LINE:
        return tr("Drawing {0} line(s) in new scratch layer '{1}'.")
    if kind == POLYGON:
        return tr("Drawing {0} polygon(s) in new scratch layer '{1}'.")
    return tr("Drawing {0} feature(s) in new scratch layer '{1}'.")


def _append_summary(kind: str) -> str:
    if kind == POINT:
        return tr("Adding {0} point(s) to '{1}'.")
    if kind == LINE:
        return tr("Adding {0} line(s) to '{1}'.")
    if kind == POLYGON:
        return tr("Adding {0} polygon(s) to '{1}'.")
    return tr("Adding {0} feature(s) to '{1}'.")
