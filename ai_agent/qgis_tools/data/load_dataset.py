from typing import Any

from qgis.core import QgsProject, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.data.catalogue import (
    GEOBOUNDARIES_LEVELS,
    KIND_VECTOR,
    NATURAL_EARTH_10M_ONLY,
    NATURAL_EARTH_LAYERS,
    NATURAL_EARTH_SCALES,
    dataset,
)
from ai_agent.qgis_tools.data.http import get_bytes, get_json
from ai_agent.qgis_tools.data.storage import TEMP_NOTE, target_path

NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_{scale}_{layer}.geojson"
)
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{country}/{level}/"
DEFAULT_SCALE = "50m"
MAX_BYTES = 120 * 1024 * 1024
GEOJSON = ".geojson"


class LoadDatasetTool(BaseTool):
    name = "load_dataset"
    description = (
        "Download an open vector dataset from the catalogue — Natural Earth world layers or "
        "geoBoundaries administrative boundaries — and add it to the project as a layer."
    )
    skill = "data"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = True
    constraints = [
        "natural-earth needs layer (and optionally scale)",
        "geoboundaries needs country (ISO alpha-3) and level",
    ]
    examples = ["Add world countries", "Load the regions of Kenya", "Add the rivers of the world in detail"]
    params_schema = [
        {"name": "dataset", "type": "string", "description": "natural-earth or geoboundaries"},
        {
            "name": "layer",
            "type": "string",
            "description": "natural-earth layer",
            "enum": list(NATURAL_EARTH_LAYERS),
            "required": False,
        },
        {
            "name": "scale",
            "type": "string",
            "description": f"natural-earth scale; default {DEFAULT_SCALE}",
            "enum": list(NATURAL_EARTH_SCALES),
            "required": False,
        },
        {"name": "country", "type": "string", "description": "geoboundaries: ISO alpha-3, e.g. KEN", "required": False},
        {
            "name": "level",
            "type": "string",
            "description": "geoboundaries: ADM0 country … ADM2 districts",
            "enum": list(GEOBOUNDARIES_LEVELS),
            "required": False,
        },
        {
            "name": "detailed",
            "type": "boolean",
            "description": "geoboundaries: full-resolution borders instead of the simplified ones",
            "required": False,
        },
        {"name": "name", "type": "string", "description": "Layer name", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = dataset(params.get("dataset") or "", KIND_VECTOR)
        prepared = {**params, "dataset": entry.id}
        if entry.id == "natural-earth":
            prepared["layer"], prepared["scale"] = _natural_earth(params)
        else:
            prepared["country"], prepared["level"] = _geoboundaries(params)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        if str(params.get("dataset") or "") == "geoboundaries":
            return tr("Downloading {0} boundaries of {1} from geoBoundaries.").format(
                str(params.get("level") or ""), str(params.get("country") or "")
            )
        return tr("Downloading Natural Earth {0}.").format(str(params.get("layer") or ""))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = dataset(params.get("dataset") or "", KIND_VECTOR)
        if entry.id == "natural-earth":
            layer_key, scale = _natural_earth(params)
            url = NATURAL_EARTH_URL.format(scale=scale, layer=NATURAL_EARTH_LAYERS[layer_key])
            title, licence = f"{layer_key.replace('_', ' ').capitalize()} ({scale})", entry.license
        else:
            country, level = _geoboundaries(params)
            meta = get_json(GEOBOUNDARIES_API.format(country=country, level=level))
            if isinstance(meta, list):
                meta = meta[0] if meta else {}
            key = "gjDownloadURL" if params.get("detailed") else "simplifiedGeometryGeoJSON"
            url = str((meta or {}).get(key) or (meta or {}).get("gjDownloadURL") or "")
            if not url:
                raise ValueError(f"geoBoundaries has no {level} layer for {country}. Try a coarser level.")
            title, licence = f"{meta.get('boundaryName') or country} {level}", str(meta.get("boundaryLicense") or "")
        name = str(params.get("name") or "").strip() or title
        path, temporary = target_path(name, GEOJSON)
        with open(path, "wb") as handle:
            handle.write(get_bytes(url, MAX_BYTES))
        layer = QgsVectorLayer(path, name, "ogr")
        if not layer.isValid():
            raise ValueError(f"The download from {url} is not a readable layer.")
        QgsProject.instance().addMapLayer(layer)
        result: dict[str, Any] = {"layer": layer.name(), "features": layer.featureCount(), "file": path}
        if licence:
            result["license"] = licence
        if temporary:
            result["storage_note"] = TEMP_NOTE
        return result


def _natural_earth(params: dict[str, Any]) -> tuple[str, str]:
    layer = str(params.get("layer") or "").strip()
    if layer not in NATURAL_EARTH_LAYERS:
        raise ValueError(f"natural-earth needs layer, one of: {', '.join(NATURAL_EARTH_LAYERS)}.")
    scale = str(params.get("scale") or "").strip() or ("10m" if layer in NATURAL_EARTH_10M_ONLY else DEFAULT_SCALE)
    if scale not in NATURAL_EARTH_SCALES:
        raise ValueError(f"scale is one of {', '.join(NATURAL_EARTH_SCALES)}.")
    if layer in NATURAL_EARTH_10M_ONLY and scale != "10m":
        raise ValueError(f"Natural Earth publishes {layer} at 10m only.")
    return layer, scale


def _geoboundaries(params: dict[str, Any]) -> tuple[str, str]:
    country = str(params.get("country") or "").strip().upper()
    if len(country) != 3 or not country.isalpha():
        raise ValueError("geoboundaries needs country as an ISO alpha-3 code such as KEN, FRA or RUS.")
    level = str(params.get("level") or "ADM1").strip().upper()
    if level not in GEOBOUNDARIES_LEVELS:
        raise ValueError(f"level is one of {', '.join(GEOBOUNDARIES_LEVELS)}.")
    return country, level
