import datetime
from typing import Any
from urllib.parse import quote, urlencode

from qgis.core import QgsDataSourceUri, QgsProject, QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.data.catalogue import KIND_SERVICE, dataset
from ai_agent.qgis_tools.data.dataset import SERVICE_WFS, SERVICE_WMS, Dataset, ServiceLayer
from ai_agent.qgis_tools.data.view import show_coverage

DATE_SLOT = "{date}"
WMS_CRS = "EPSG:3857"
WFS_CRS = "EPSG:4326"


class LoadServiceTool(BaseTool):
    name = "load_service"
    description = (
        "Add a layer of a public web map service from the catalogue — satellite mosaics, NASA daily imagery, "
        "bathymetry, national aerial photos and maps, administrative units as WFS — to the project."
    )
    skill = "data"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = True
    constraints = ["dataset is a service id from find_open_data and layer one of its layer keys"]
    examples = ["Add yesterday's NASA satellite picture", "Add French aerial photos", "Add Dutch municipalities"]
    params_schema = [
        {"name": "dataset", "type": "string", "description": "Service dataset id, e.g. nasa-gibs"},
        {"name": "layer", "type": "string", "description": "Layer key from find_open_data, e.g. modis_true_color"},
        {
            "name": "date",
            "type": "string",
            "description": "Day YYYY-MM-DD for daily imagery; default yesterday",
            "required": False,
        },
        {"name": "name", "type": "string", "description": "Layer name", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        entry, layer = _chosen(params)
        prepared = {**params, "dataset": entry.id, "layer": layer.key}
        if DATE_SLOT in layer.source:
            prepared["date"] = _day(params.get("date"))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Adding {0} from {1}.").format(str(params.get("layer") or ""), str(params.get("dataset") or ""))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        entry, layer = _chosen(params)
        name = str(params.get("name") or "").strip() or f"{entry.title} — {layer.title}"
        protocol = layer.protocol or entry.service
        if protocol == SERVICE_WFS:
            added: Any = QgsVectorLayer(_wfs_source(entry, layer), name, "WFS")
        else:
            source = _wms_source(entry, layer) if protocol == SERVICE_WMS else _xyz_source(layer, params)
            added = QgsRasterLayer(source, name, "wms")
        if not added.isValid():
            raise ValueError(f"QGIS could not open {entry.title} — {layer.title}. The service may be down; try later.")
        _credit(added, entry.attribution)
        project = QgsProject.instance()
        if protocol == SERVICE_WFS:
            project.addMapLayer(added)
        else:
            # Tiles and WMS pictures are backdrops: they go under the vector layers.
            project.addMapLayer(added, False)
            root = project.layerTreeRoot()
            root.insertLayer(len(root.children()), added)
        result: dict[str, Any] = {"layer": added.name(), "service": protocol, "license": entry.license}
        if show_coverage(entry.bbox):
            result["map_moved_to"] = entry.coverage
        if entry.notes:
            result["notes"] = list(entry.notes)
        return result


def _chosen(params: dict[str, Any]) -> tuple[Dataset, ServiceLayer]:
    entry = dataset(params.get("dataset") or "", KIND_SERVICE)
    wanted = str(params.get("layer") or "").strip()
    for layer in entry.layers:
        if layer.key == wanted:
            return entry, layer
    keys = ", ".join(layer.key for layer in entry.layers)
    raise ValueError(f"{entry.id} has no layer '{wanted}'. Its layers: {keys}.")


def _day(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return (datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)).isoformat()
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"date '{text}' is not a day like 2026-06-30.") from None


def _xyz_source(layer: ServiceLayer, params: dict[str, Any]) -> str:
    url = layer.source.replace(DATE_SLOT, _day(params.get("date"))) if DATE_SLOT in layer.source else layer.source
    return f"type=xyz&url={quote(url, safe='')}&zmin=0&zmax={layer.zmax}"


def _wms_source(entry: Dataset, layer: ServiceLayer) -> str:
    return urlencode(
        {"url": entry.endpoint, "layers": layer.source, "crs": WMS_CRS, "format": "image/png", "styles": ""}
    )


def _wfs_source(entry: Dataset, layer: ServiceLayer) -> str:
    uri = QgsDataSourceUri()
    for key, value in (
        ("url", entry.endpoint),
        ("typename", layer.source),
        ("version", "auto"),
        ("srsname", WFS_CRS),
        # Only what the map shows: thirty-five thousand French communes must not download at once.
        ("restrictToRequestBBOX", "1"),
        ("pagingEnabled", "true"),
    ):
        uri.setParam(key, value)
    return uri.uri(False)


def _credit(layer: Any, attribution: str) -> None:
    if not attribution:
        return
    try:
        layer.serverProperties().setAttribution(attribution)
    except AttributeError:
        pass
