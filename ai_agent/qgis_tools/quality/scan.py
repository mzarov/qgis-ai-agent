# Runs on the main thread: one pass, stored fields only, no geometry for a table, capped.

from contextlib import suppress
from hashlib import blake2b
from typing import Any

from qgis.core import Qgis, QgsFeatureRequest, QgsGeometry, QgsMessageLog, QgsVectorLayer

from ai_agent.qgis_tools.common.layers import enum_name
from ai_agent.qgis_tools.quality.tally import Bounds, Tally

MAX_FEATURES = 50_000
MAX_CHECKED_FIELDS = 100
KEY_BYTES = 16
COORD_DIGITS = 6
EXPRESSION_ORIGIN = "expression"
UNREADABLE_REASON = "GEOS could not read the geometry"
UNKNOWN_REASON = "invalid"
LOG_TAG = "AI Agent"


def stored_fields(layer: QgsVectorLayer) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    fields = layer.fields()
    for index in range(fields.count()):
        with suppress(Exception):
            if EXPRESSION_ORIGIN in enum_name(fields.fieldOrigin(index)).lower():
                continue
        found.append((index, fields.at(index).name()))
    return found


def scan_layer(layer: QgsVectorLayer) -> tuple[Tally, bool, int]:
    fields = stored_fields(layer)
    checked_fields = fields[:MAX_CHECKED_FIELDS]
    indexes = [index for index, _ in checked_fields]
    tally = Tally([name for _, name in checked_fields])
    spatial = _is_spatial(layer)
    partial = False
    for feature in layer.getFeatures(_request(indexes, spatial)):
        if tally.checked >= MAX_FEATURES:
            partial = True
            break
        tally.checked += 1
        if spatial:
            _check_geometry(feature, tally)
        attributes = feature.attributes()
        tally.add_values([attributes[index] if index < len(attributes) else None for index in indexes])
    return tally, partial, len(fields) - len(checked_fields)


def invalid_reason(geometry: QgsGeometry) -> str:
    try:
        errors = geometry.validateGeometry(Qgis.GeometryValidationEngine.Geos)
    except Exception:
        return UNKNOWN_REASON
    if not errors:
        return UNKNOWN_REASON
    error = errors[0]
    text = str(error.what() or UNKNOWN_REASON)
    with suppress(Exception):
        if error.hasWhere():
            where = error.where()
            text += f" at {_number(where.x())}, {_number(where.y())}"
    return text


def _request(indexes: list[int], spatial: bool) -> QgsFeatureRequest:
    request = QgsFeatureRequest()
    request.setSubsetOfAttributes(indexes)
    if not spatial:
        request.setFlags(Qgis.FeatureRequestFlag.NoGeometry)
    request.setLimit(MAX_FEATURES + 1)
    return request


def _is_spatial(layer: QgsVectorLayer) -> bool:
    try:
        return bool(layer.isSpatial())
    except Exception:
        return True


def _check_geometry(feature: Any, tally: Tally) -> None:
    feature_id = int(feature.id())
    geometry = feature.geometry() if feature.hasGeometry() else None
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        tally.add_empty(feature_id)
        return
    with suppress(Exception):
        box = geometry.boundingBox()
        tally.add_bounds(Bounds(box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))
    try:
        valid = bool(geometry.isGeosValid())
    except Exception:
        tally.add_invalid(feature_id, UNREADABLE_REASON)
        return
    if not valid:
        tally.add_invalid(feature_id, invalid_reason(geometry) if tally.wants_reason() else "")
    try:
        tally.add_geometry(feature_id, _geometry_key(geometry))
    except Exception as error:
        QgsMessageLog.logMessage(
            f"check_layer: feature {feature_id} has no comparable geometry: {error}", LOG_TAG, Qgis.MessageLevel.Warning
        )


def _geometry_key(geometry: QgsGeometry) -> bytes:
    normalized = QgsGeometry(geometry)
    normalized.normalize()
    return blake2b(bytes(normalized.asWkb()), digest_size=KEY_BYTES).digest()


def _number(value: float) -> str:
    return f"{float(value):.{COORD_DIGITS}f}".rstrip("0").rstrip(".")
