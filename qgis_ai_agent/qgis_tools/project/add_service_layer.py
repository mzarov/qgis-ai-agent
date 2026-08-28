from typing import Any
from urllib.parse import quote, urlencode

from qgis.core import QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import crs_authid, safe_feature_count
from qgis_ai_agent.qgis_tools.project.tree import layer_names, project

WMS = "wms"
WFS = "wfs"
SERVICES = (WMS, WFS)
DEFAULT_CRS = "EPSG:3857"
DEFAULT_IMAGE_FORMAT = "image/png"


class AddServiceLayerTool(BaseTool):
    name = "add_service_layer"
    description = (
        "Add a layer from an OGC web service: WMS for rendered map images, WFS "
        "for real vector features you can query. Needs the service URL and the "
        "layer name the service publishes."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "The service URL and the published layer name are both required",
        "The service must be reachable and public — the plugin sends no credentials",
    ]
    examples = [
        "Add the WMS layer of the topographic base",
        "Load the districts from the WFS service",
    ]
    params_schema = [
        {
            "name": "service",
            "type": "string",
            "enum": list(SERVICES),
            "description": "wms for a picture service, wfs for vector features",
            "required": True,
        },
        {
            "name": "url",
            "type": "string",
            "description": "Service endpoint, without the request parameters",
            "required": True,
        },
        {
            "name": "layer",
            "type": "string",
            "description": "Layer name as published by the service (its typename for WFS)",
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name in the project. Defaults to the published name.",
            "required": False,
        },
        {
            "name": "crs",
            "type": "string",
            "description": f"CRS to request, e.g. EPSG:4326 (default {DEFAULT_CRS})",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        service = _checked_service(params.get("service"))
        url = _checked_url(params.get("url"))
        published = str(params.get("layer") or "").strip()
        if not published:
            raise ValueError("layer is required — the name the service publishes, not a name you invent.")
        title = str(params.get("name") or "").strip() or published
        if title in layer_names():
            raise ValueError(f"A layer named '{title}' is already in the project. Give another name.")
        prepared = dict(params)
        prepared["service"] = service
        prepared["url"] = url
        prepared["name"] = title
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        service = str(params.get("service") or "").strip().upper()
        published = str(params.get("layer") or "").strip()
        return tr("Adding {0} layer '{1}'.").format(service, published)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        service = _checked_service(params.get("service"))
        url = _checked_url(params.get("url"))
        published = str(params.get("layer") or "").strip()
        title = str(params.get("name") or "").strip() or published
        crs = str(params.get("crs") or DEFAULT_CRS).strip()
        layer = _built(service, url, published, title, crs)
        if not layer.isValid():
            raise ValueError(
                f"QGIS could not open '{published}' from {url}. Check the URL, the published "
                "layer name and that the service answers without a login."
            )
        project().addMapLayer(layer)
        described: dict[str, Any] = {"name": layer.name(), "service": service, "crs": crs_authid(layer) or crs}
        if service == WFS:
            described["feature_count"] = safe_feature_count(layer)
        return described


def _built(service: str, url: str, published: str, title: str, crs: str) -> Any:
    if service == WMS:
        source = urlencode({"url": url, "layers": published, "crs": crs, "format": DEFAULT_IMAGE_FORMAT, "styles": ""})
        return QgsRasterLayer(source, title, WMS)
    source = f"{url}?service=WFS&version=1.1.0&request=GetFeature&typename={quote(published, safe='')}&srsname={crs}"
    return QgsVectorLayer(source, title, WFS)


def _checked_service(raw: Any) -> str:
    service = str(raw or "").strip().lower()
    if service not in SERVICES:
        raise ValueError(f"Unknown service '{raw}'. Available: {', '.join(SERVICES)}.")
    return service


def _checked_url(raw: Any) -> str:
    url = str(raw or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"The service url must start with http:// or https://, got '{url}'.")
    return url.split("?")[0]
