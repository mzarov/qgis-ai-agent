from collections.abc import Callable
from typing import Any

from qgis.core import Qgis, QgsMapLayer, QgsMessageLog, QgsProject, QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.layers import (
    feature_count_if_cheap,
    find_layer_by_name,
    geometry_type_name,
    layer_kind,
    layer_reference,
)
from ai_agent.qgis_tools.quality import findings
from ai_agent.qgis_tools.quality.raster import FILE_PROVIDER, raster_findings
from ai_agent.qgis_tools.quality.scan import MAX_FEATURES, scan_layer

LOG_TAG = "AI Agent"
KIND_VECTOR = "vector"
KIND_RASTER = "raster"
NO_GEOMETRY = "none"
CRS_UNKNOWN = "unknown"
NO_FEATURES_NOTE = "The layer has no features."
NO_GEOMETRY_NOTE = "The layer has no geometry: only its fields were checked."
# What a person reads for each problem the check found; the model reads the payload's counts.
PROBLEM_WORDS: dict[str, Callable[[int], str]] = {
    findings.PROBLEM_CRS: lambda count: tr("no valid CRS"),
    findings.PROBLEM_COORDINATES: lambda count: tr("coordinates do not fit the CRS"),
    findings.PROBLEM_EXTENT: lambda count: tr("empty extent"),
    findings.PROBLEM_INVALID: lambda count: tr_n("%n feature(s) with invalid geometry", count),
    findings.PROBLEM_EMPTY: lambda count: tr_n("%n feature(s) without geometry", count),
    findings.PROBLEM_DUPLICATE: lambda count: tr_n("%n geometry duplicate(s)", count),
    findings.PROBLEM_EMPTY_FIELDS: lambda count: tr_n("%n empty field(s)", count),
}


class CheckLayerTool(BaseTool):
    name = "check_layer"
    description = (
        "Check one layer's data for errors: invalid geometries (GEOS validity, with the reason), features "
        "without geometry, repeated geometries, fields with missing values or none at all, coordinates that "
        "contradict the layer CRS, an invalid CRS; for a raster its bands, nodata, CRS and extent. `problems` "
        "holds the counts and is empty for a clean layer; duplicate_geometry counts the extra copies. "
        f"Samples are capped, at most {MAX_FEATURES} features are read, and `suggestions` names the fix "
        "for each problem."
    )
    skill = "quality"
    safety = SAFETY_READ
    external_effect = False
    network_access = False
    egress = EGRESS_FEATURE_VALUES
    constraints = ["The layer must be a vector or raster layer"]
    examples = ["Check my data for errors", "Are there broken geometries in the parcels?"]
    params_schema = [params.layer_name()]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = str(params.get("layer_name") or "").strip()
        if not layer_name:
            return tr("Checking the layer for data errors.")
        return tr("Checking layer '{0}' for data errors.").format(layer_name)

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        problems = payload.get("problems")
        if not isinstance(problems, dict):
            return ""
        if payload.get("kind") == KIND_RASTER:
            head = tr_n("Checked %n band(s)", int(payload.get("band_count") or 0))
        elif payload.get("partial"):
            head = tr_n("Checked the first %n feature(s)", int(payload.get("checked_features") or 0))
        else:
            head = tr_n("Checked %n feature(s)", int(payload.get("checked_features") or 0))
        words = [PROBLEM_WORDS[name](int(count)) for name, count in problems.items() if name in PROBLEM_WORDS]
        return f"{head}: {', '.join(words or [tr('no problems found')])}"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        kind = layer_kind(layer)
        if kind not in (KIND_VECTOR, KIND_RASTER):
            raise ValueError(
                f"Layer '{layer.name()}' is neither a vector nor a raster layer; check_layer reads only those."
            )
        label, crs_valid, geographic = crs_facts(layer)
        result: dict[str, Any] = {**layer_reference(layer), "kind": kind}
        if isinstance(layer, QgsVectorLayer):
            block, coordinates = self._check_vector(layer, label, crs_valid, geographic)
        else:
            block, coordinates = raster_findings(layer, geographic, crs_valid)
            result["crs"] = label
        result.update(block)
        spread = findings.crs_spread(project_crs_labels())
        if spread:
            result["project_crs"] = spread
        result["suggestions"] = findings.suggestions(
            result["problems"], coordinates, crs_spread_found=bool(spread), nodata_missing="nodata_note" in result
        )
        QgsMessageLog.logMessage(
            f"check_layer '{layer.name()}': {result['problems'] or 'no problems'}", LOG_TAG, Qgis.MessageLevel.Info
        )
        return result

    @staticmethod
    def _check_vector(
        layer: QgsVectorLayer, label: str, crs_valid: bool, geographic: bool
    ) -> tuple[dict[str, Any], str]:
        """The vector part of the payload and the kind of coordinate problem, "" when there is none."""
        tally, partial, fields_left_out = scan_layer(layer)
        spatial = is_spatial(layer)
        block: dict[str, Any] = {
            "geometry": geometry_type_name(layer) if spatial else NO_GEOMETRY,
            "crs": label,
            "checked_features": tally.checked,
        }
        if partial:
            block["partial"] = True
            block["scan_note"] = partial_note(tally.checked, feature_count_if_cheap(layer))
        elif not tally.checked:
            block["scan_note"] = NO_FEATURES_NOTE
        block.update(findings.vector_findings(tally, geographic, crs_valid))
        if not spatial:
            block["geometry_note"] = NO_GEOMETRY_NOTE
        if fields_left_out:
            block["fields_note"] = f"{fields_left_out} more fields were not checked."
        return block, findings.coordinate_kind(geographic, tally.bounds) if crs_valid else ""


def crs_facts(layer: QgsMapLayer) -> tuple[str, bool, bool]:
    """The layer CRS as a label (authid, else its name), whether it is valid, whether it is geographic."""
    try:
        crs = layer.crs()
        if not crs.isValid():
            return CRS_UNKNOWN, False, False
        return str(crs.authid() or crs.description() or CRS_UNKNOWN), True, bool(crs.isGeographic())
    except Exception:
        return CRS_UNKNOWN, False, False


def project_crs_labels() -> list[str]:
    """The CRS of every layer holding the user's own data; a web basemap is reprojected and says nothing."""
    labels: list[str] = []
    try:
        layers = list(QgsProject.instance().mapLayers().values())
    except Exception:
        return labels
    for layer in layers:
        if isinstance(layer, QgsVectorLayer):
            own = is_spatial(layer)
        else:
            own = isinstance(layer, QgsRasterLayer) and str(layer.providerType() or "").lower() == FILE_PROVIDER
        label, valid, _ = crs_facts(layer)
        if own and valid:
            labels.append(label)
    return labels


def is_spatial(layer: QgsVectorLayer) -> bool:
    try:
        return bool(layer.isSpatial())
    except Exception:
        return True


def partial_note(checked: int, total: int | None) -> str:
    """What a scan stopped at the cap covered: the first `checked` features, of `total` when counting is cheap."""
    if total is not None and total > checked:
        return f"Checked the first {checked} features of {total}; the counts cover those only."
    return f"Checked the first {checked} features; the layer has more, the counts cover those only."
