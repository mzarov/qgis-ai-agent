from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsRasterLayer

from ai_agent.i18n import tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.data.catalogue import KIND_IMAGERY, TRUE_COLOR, Dataset, dataset
from ai_agent.qgis_tools.data.stac import asset_href, item, scene_date, signed
from ai_agent.qgis_tools.data.storage import TEMP_NOTE, target_path

MAX_ITEMS = 6
VSICURL = "/vsicurl/"
LOG_TAG = "AI Agent"
LINK_NOTE = (
    "The layers read the files in place over the internet with a signed link that expires "
    "{expiry}. After that they stop drawing: load them again, or export them with export_layer "
    "to keep a local copy."
)


class LoadImageryTool(BaseTool):
    name = "load_imagery"
    description = (
        "Add satellite scenes or raster tiles found by search_imagery to the project as raster "
        "layers. They are read in place from the Planetary Computer, nothing is downloaded whole."
    )
    skill = "data"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = True
    constraints = [
        "item_ids come from search_imagery for the same collection",
        f"At most {MAX_ITEMS} scenes per call",
    ]
    examples = ["Load the clearest scene", "Load all four DEM tiles"]
    params_schema = [
        {"name": "collection", "type": "string", "description": "The dataset id used in search_imagery"},
        {
            "name": "item_ids",
            "type": "array",
            "items": {"type": "string"},
            "description": "Scene ids from search_imagery",
        },
        {
            "name": "asset",
            "type": "string",
            "description": "Which band or picture to load; leave out for the dataset's default (see find_open_data)",
            "required": False,
        },
        {"name": "name", "type": "string", "description": "Layer name prefix", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = dataset(params.get("collection") or "", KIND_IMAGERY)
        ids = _item_ids(params)
        asset = _asset(entry, params.get("asset"))
        return {**params, "collection": entry.id, "item_ids": ids, "asset": asset}

    def summarize_call(self, params: dict[str, Any]) -> str:
        ids = params.get("item_ids") or []
        count = len(ids) if isinstance(ids, list) else 1
        return tr_n("Loading %n scene(s) of {0} from the Planetary Computer.", count).format(
            str(params.get("collection") or "")
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = dataset(params.get("collection") or "", KIND_IMAGERY)
        asset = _asset(entry, params.get("asset"))
        prefix = str(params.get("name") or "").strip() or entry.title
        added: list[dict[str, Any]] = []
        temporary = False
        expiry = ""
        for item_id in _item_ids(params):
            found = item(entry.id, item_id)
            name = f"{prefix} {scene_date(found.get('properties') or {})}".strip()
            if asset == TRUE_COLOR and entry.rgb:
                source, in_temp, expiry = _stacked(entry, found, name)
                temporary = temporary or in_temp
            else:
                link, expiry = signed(asset_href(found, asset))
                source = VSICURL + link
            layer = QgsRasterLayer(source, name, "gdal")
            if not layer.isValid():
                raise ValueError(f"QGIS could not open scene '{item_id}' ({asset}). The service may be busy.")
            QgsProject.instance().addMapLayer(layer)
            added.append({"layer": layer.name(), "id": layer.id(), "scene": item_id, "asset": asset})
        result: dict[str, Any] = {"added": added, "note": LINK_NOTE.format(expiry=expiry or "within a day")}
        if temporary:
            result["storage_note"] = TEMP_NOTE
        return result


def _item_ids(params: dict[str, Any]) -> list[str]:
    raw = params.get("item_ids")
    if isinstance(raw, str):
        raw = [raw]
    ids = [str(value).strip() for value in raw or [] if str(value).strip()] if isinstance(raw, list) else []
    if not ids:
        raise ValueError("item_ids is empty. Pass scene ids from search_imagery.")
    if len(ids) > MAX_ITEMS:
        raise ValueError(f"{len(ids)} scenes at once is too many; load at most {MAX_ITEMS} per call.")
    return list(dict.fromkeys(ids))


def _asset(entry: Dataset, raw: Any) -> str:
    asset = str(raw or "").strip() or entry.default_asset
    if asset not in entry.assets:
        raise ValueError(f"{entry.id} has no asset '{asset}'. Available: {', '.join(entry.assets)}.")
    return asset


def _stacked(entry: Dataset, found: dict[str, Any], name: str) -> tuple[str, bool, str]:
    """One RGB layer from separate band files: a small VRT pointing at the signed remote bands."""
    from osgeo import gdal

    links = [signed(asset_href(found, band)) for band in entry.rgb]
    bands = [VSICURL + link for link, _expiry in links]
    path, temporary = target_path(name, ".vrt")
    options = gdal.BuildVRTOptions(separate=True)
    built = gdal.BuildVRT(path, bands, options=options)
    if built is None:
        raise ValueError(f"Could not stack the bands of scene '{found.get('id')}' into one picture.")
    built = None  # Closing the dataset writes the VRT to disk.
    QgsMessageLog.logMessage(f"Stacked true colour into {path}.", LOG_TAG, Qgis.MessageLevel.Info)
    return path, temporary, links[0][1]
