"""Where drawn features land: a new scratch layer or an existing vector layer."""

from typing import Any

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsMemoryProviderUtils,
    QgsProject,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)

from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.common.layers import (
    find_layer_by_id,
    find_layer_by_name,
    geometry_type_name,
    layer_reference,
)
from ai_agent.qgis_tools.draw.attributes import check_existing_fields, coerced_rows, qgs_fields
from ai_agent.qgis_tools.draw.coordinates import (
    LINE,
    POINT,
    POLYGON,
    UTM_KEYWORD,
    Vertex,
    build_geometry,
    checked_crs,
    crs_label,
    transformed_points,
    utm_crs_for,
)

MEMORY_PROVIDER = "memory"
SCRATCH_NOTE = "A scratch layer lives in memory until QGIS closes; export_layer keeps it as a file."
SOURCE_NOTE = "The features were committed to the layer's data source; Undo does not remove them."


def draw_new_layer(
    name: str,
    geometry: str,
    source: QgsCoordinateReferenceSystem,
    target: QgsCoordinateReferenceSystem,
    shapes: list[list[Vertex]],
    rows: list[dict[str, Any]],
    schema: dict[str, str],
) -> dict[str, Any]:
    """Build a memory layer with the features, then add it to the project; nothing is added on failure."""
    check_free_name(name)
    wkb_types = {POINT: Qgis.WkbType.Point, LINE: Qgis.WkbType.LineString, POLYGON: Qgis.WkbType.Polygon}
    layer = QgsMemoryProviderUtils.createMemoryLayer(name, qgs_fields(schema), wkb_types[geometry], target)
    if layer is None or not layer.isValid():
        raise ValueError(f"QGIS could not create the scratch layer '{name}'.")
    features = []
    for vertices, row in zip(shapes, coerced_rows(schema, rows), strict=False):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(build_geometry(geometry, transformed_points(vertices, source, target)))
        for field_name, value in row.items():
            feature.setAttribute(field_name, value)
        features.append(feature)
    if features and not _added(layer.dataProvider().addFeatures(features)):
        raise ValueError(f"The memory provider refused the features for '{name}'. Nothing was added to the project.")
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return {
        **layer_reference(layer),
        "created": True,
        "geometry": geometry,
        "crs": crs_label(target, target.toWkt()),
        "added": len(features),
        "note": SCRATCH_NOTE,
    }


def append_to_layer(
    layer: QgsVectorLayer,
    geometry: str,
    source: QgsCoordinateReferenceSystem,
    shapes: list[list[Vertex]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add the features in one edit session, committed or rolled back as a whole."""
    check_existing_target(layer, geometry)
    check_existing_fields(layer, rows)
    fields = layer.fields()
    features = []
    for vertices, row in zip(shapes, rows, strict=False):
        shape = build_geometry(geometry, transformed_points(vertices, source, layer.crs()))
        values = {fields.indexFromName(name): value for name, value in row.items()}
        feature = QgsVectorLayerUtils.createFeature(layer, shape, values)
        # Matches the layer's multi-part and Z/M flavour, which a plain 2D geometry may lack.
        features.extend(QgsVectorLayerUtils.makeFeatureCompatible(feature, layer))
    with edit_session(layer, "the new features"):
        if not layer.addFeatures(features):
            raise ValueError(f"QGIS refused to add the features to '{layer.name()}'.")
    layer.triggerRepaint()
    return {
        **layer_reference(layer),
        "created": False,
        "geometry": geometry,
        "added": len(features),
        "note": SCRATCH_NOTE if is_memory(layer) else SOURCE_NOTE,
    }


def new_layer_crs(raw: Any, source: QgsCoordinateReferenceSystem, shapes: list[list[Vertex]]) -> Any:
    text = str(raw or "").strip()
    if not text:
        return source
    if text.lower() == UTM_KEYWORD:
        return utm_crs_for(shapes, source)
    return checked_crs(text, "layer_crs")


def existing_layer(params: dict[str, Any]) -> QgsVectorLayer:
    layer_id = str(params.get("layer_id") or "").strip()
    layer = find_layer_by_id(layer_id) if layer_id else find_layer_by_name(str(params.get("layer_name") or ""))
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer; draw into a new_layer_name instead.")
    return layer


def check_existing_target(layer: QgsVectorLayer, geometry: str) -> None:
    kind = geometry_type_name(layer)
    if kind != geometry:
        raise ValueError(
            f"Layer '{layer.name()}' holds {kind or 'no'} geometries, not {geometry}s. "
            "Pick a layer of that geometry or create one with new_layer_name."
        )
    if layer.isEditable():
        raise ValueError(
            f"Layer '{layer.name()}' is in an edit session already. Ask the user to save or discard those edits first."
        )


def check_free_name(name: str) -> None:
    if QgsProject.instance().mapLayersByName(name):
        raise ValueError(
            f"A layer named '{name}' is already in the project. Pick another new_layer_name, "
            "or append to it with layer_name."
        )


def inside_extent(layer: QgsVectorLayer, crs_text: str, vertices: list[Vertex]) -> bool:
    """Whether the vertices, given in the layer's own CRS, fall inside its current extent."""
    try:
        if not vertices or layer.crs().authid() != crs_text:
            return False
        extent = layer.extent()
        if extent.isEmpty():
            return False
        bounds = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    except Exception:
        return False
    xmin, ymin, xmax, ymax = (float(edge) for edge in bounds)
    return all(xmin <= x <= xmax and ymin <= y <= ymax for x, y in vertices)


def is_memory(layer: Any) -> bool:
    try:
        return str(layer.providerType()) == MEMORY_PROVIDER
    except Exception:
        return False


def _added(result: Any) -> bool:
    # A provider's addFeatures returns (ok, features) in PyQGIS.
    return bool(result[0] if isinstance(result, tuple) else result)
