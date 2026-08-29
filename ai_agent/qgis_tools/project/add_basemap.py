from typing import Any
from urllib.parse import quote

from qgis.core import QgsRasterLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.project.tree import layer_names, layer_tree, project

WMS_PROVIDER = "wms"
REQUIRED_PLACEHOLDERS = ("{z}", "{x}", "{y}")
PRESETS = {
    "osm": (
        "OpenStreetMap",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors",
    ),
    "opentopomap": (
        "OpenTopoMap",
        "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
    ),
    "carto-positron": (
        "CARTO Positron",
        "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors, © CARTO",
    ),
    "carto-dark": (
        "CARTO Dark Matter",
        "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors, © CARTO",
    ),
    "esri-imagery": (
        "Esri World Imagery",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "© Esri, Maxar, Earthstar Geographics",
    ),
}


class AddBasemapTool(BaseTool):
    name = "add_basemap"
    description = (
        "Add an XYZ tile basemap to the project, placed under all other layers. "
        "Pick a preset, or pass a custom tile URL template with {z}/{x}/{y}. "
        "The layer needs internet access to draw."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["A custom url must contain the {z}, {x} and {y} placeholders"]
    examples = ["Add an OpenStreetMap basemap", "Put satellite imagery under my layers"]
    params_schema = [
        {
            "name": "preset",
            "type": "string",
            "enum": sorted(PRESETS),
            "description": "A known basemap; osm is the safe default",
            "required": False,
        },
        {
            "name": "url",
            "type": "string",
            "description": "Custom XYZ template, e.g. https://host/tiles/{z}/{x}/{y}.png",
            "required": False,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name in the project. Defaults to the preset title.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        title, url, _ = _resolved(params)
        if title in layer_names():
            raise ValueError(f"A layer named '{title}' is already in the project. Give another name.")
        prepared = dict(params)
        prepared["name"] = title
        prepared["url"] = url
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        try:
            title, _, _ = _resolved(params)
        except ValueError:
            return tr("Adding a basemap.")
        return tr("Adding basemap '{0}' under the other layers.").format(title)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        title, url, attribution = _resolved(params)
        layer = QgsRasterLayer(_xyz_source(url), title, WMS_PROVIDER)
        if not layer.isValid():
            raise ValueError(f"QGIS could not open the tile service at {url}.")
        project().addMapLayer(layer, False)
        layer_tree().addLayer(layer)
        return {"name": layer.name(), "url": url, "attribution": attribution, "placed": "bottom"}


def _resolved(params: dict[str, Any]) -> tuple[str, str, str]:
    preset_name = (params.get("preset") or "").strip().lower()
    custom_url = (params.get("url") or "").strip()
    given_name = (params.get("name") or "").strip()
    if preset_name:
        if preset_name not in PRESETS:
            raise ValueError(f"Unknown basemap preset '{preset_name}'. Available: {', '.join(sorted(PRESETS))}.")
        title, url, attribution = PRESETS[preset_name]
        return given_name or title, url, attribution
    if not custom_url:
        raise ValueError(f"Give either a preset ({', '.join(sorted(PRESETS))}) or a custom url.")
    missing = [part for part in REQUIRED_PLACEHOLDERS if part not in custom_url]
    if missing:
        raise ValueError(f"The url template is missing {', '.join(missing)} — QGIS cannot request tiles without them.")
    return given_name or "Basemap", custom_url, ""


def _xyz_source(url: str) -> str:
    return f"type=xyz&url={quote(url, safe='')}&zmin=0&zmax=19"
