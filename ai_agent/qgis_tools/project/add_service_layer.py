from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from qgis.core import QgsCoordinateReferenceSystem, QgsDataSourceUri, QgsRasterLayer, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import crs_authid, feature_count_block
from ai_agent.qgis_tools.project.tree import layer_names, project

WMS = "wms"
WFS = "wfs"
SERVICES = (WMS, WFS)
DEFAULT_CRS = "EPSG:3857"
DEFAULT_IMAGE_FORMAT = "image/png"
WFS_VERSION = "1.1.0"
# The request's own parameters: QGIS writes them itself. Anything else (MapServer's map=) is the endpoint.
REQUEST_KEYS = frozenset(
    {
        "service",
        "request",
        "version",
        "layers",
        "styles",
        "format",
        "crs",
        "srs",
        "bbox",
        "width",
        "height",
        "transparent",
        "typename",
        "typenames",
        "srsname",
        "outputformat",
    }
)


class AddServiceLayerTool(BaseTool):
    name = "add_service_layer"
    description = (
        "Add a layer from an OGC web service: WMS for rendered map images, WFS "
        "for real vector features you can query. Needs the service URL and the "
        "layer name the service publishes."
    )
    skill = "project"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = True
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
        prepared["crs"] = _checked_crs(params.get("crs"))
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
        crs = _checked_crs(params.get("crs"))
        layer = _built(service, url, published, title, crs)
        if not layer.isValid():
            raise ValueError(
                f"QGIS could not open '{published}' from {url}. Check the URL, the published "
                "layer name and that the service answers without a login."
            )
        project().addMapLayer(layer)
        described: dict[str, Any] = {"name": layer.name(), "service": service, "crs": crs_authid(layer) or crs}
        if service == WFS:
            described.update(feature_count_block(layer))
        return described


def _built(service: str, url: str, published: str, title: str, crs: str) -> Any:
    if service == WMS:
        # quote, not the default quote_plus: QGIS reads "+" in a layer name as a plus.
        source = urlencode(
            {"url": url, "layers": published, "crs": crs, "format": DEFAULT_IMAGE_FORMAT, "styles": ""},
            quote_via=quote,
        )
        return QgsRasterLayer(source, title, WMS)
    # Keyed, not a request URL: there a typename's colon would need encoding, and QGIS does not decode it.
    uri = QgsDataSourceUri()
    for key, value in (("url", url), ("typename", published), ("version", WFS_VERSION), ("srsname", crs)):
        uri.setParam(key, value)
    return QgsVectorLayer(uri.uri(False), title, WFS)


def _checked_service(raw: Any) -> str:
    service = str(raw or "").strip().lower()
    if service not in SERVICES:
        raise ValueError(f"Unknown service '{raw}'. Available: {', '.join(SERVICES)}.")
    return service


def _checked_crs(raw: Any) -> str:
    text = str(raw or "").strip() or DEFAULT_CRS
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        raise ValueError(f"Unknown CRS '{text}'. Give an authority id such as EPSG:4326 or EPSG:3857.")
    authid = crs.authid()
    return authid if isinstance(authid, str) and authid else text


def _checked_url(raw: Any) -> str:
    url = str(raw or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"The service url must start with http:// or https://, got '{url}'.")
    parts = urlsplit(url)
    kept = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in REQUEST_KEYS
    ]
    return urlunsplit(parts._replace(query=urlencode(kept, quote_via=quote, safe="/:"), fragment=""))
