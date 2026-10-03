from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import crs_authid, feature_count_block, geometry_type_name, layer_reference
from ai_agent.qgis_tools.tables.coordinates import checked_wkt_crs, checked_xy_crs, guess_coordinates
from ai_agent.qgis_tools.tables.delimited import DelimitedTable, read_table
from ai_agent.qgis_tools.tables.source import open_delimited

GEOMETRY_KEYS = ("x_field", "y_field", "wkt_field", "crs")


class LoadTableTool(BaseTool):
    name = "load_table"
    description = (
        "Add a CSV/TSV/TXT file to the project through the delimited text provider: as points from x/y "
        "columns, as geometries from a WKT column, or as a plain table without geometry. Without "
        "x_field/y_field/wkt_field, coordinate columns are recognised by name (lon/lat, x/y) and used; "
        "table_only skips that."
    )
    skill = "tables"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "The file must exist and end in .csv, .tsv or .txt",
        "Named columns must exist in the header",
        "Coordinates that are not lon/lat degrees need crs",
    ]
    examples = ["Make points from cafes.csv with lon/lat", "Load stats.csv as a table"]
    params_schema = [
        {"name": "path", "type": "string", "description": "Path to the file", "required": True},
        {"name": "name", "type": "string", "description": "Layer name; the file name by default", "required": False},
        {"name": "x_field", "type": "string", "description": "Column with x / longitude", "required": False},
        {"name": "y_field", "type": "string", "description": "Column with y / latitude", "required": False},
        {"name": "wkt_field", "type": "string", "description": "Column with WKT geometry", "required": False},
        {
            "name": "crs",
            "type": "string",
            "description": "CRS of the coordinates, e.g. EPSG:32637. EPSG:4326 when they are lon/lat degrees.",
            "required": False,
        },
        {"name": "table_only", "type": "boolean", "description": "Load without geometry", "required": False},
        {
            "name": "delimiter",
            "type": "string",
            "description": "Force the delimiter: , ; tab or |. Detected when omitted.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        table = read_table(params.get("path") or "", str(params.get("delimiter") or ""))
        prepared = {key: value for key, value in params.items() if key not in GEOMETRY_KEYS}
        prepared["path"] = table.path
        prepared["delimiter"] = table.delimiter_name
        prepared["name"] = _checked_name(params, table)
        prepared.update(_geometry(params, table))
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        path = str(params.get("path") or "").strip()
        x_field, y_field = str(params.get("x_field") or ""), str(params.get("y_field") or "")
        if x_field and y_field:
            return tr("Loading points from {0} ({1}, {2}).").format(path, x_field, y_field)
        if params.get("wkt_field"):
            return tr("Loading geometries from {0} ({1}).").format(path, str(params.get("wkt_field")))
        return tr("Loading table {0}.").format(path)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        table = read_table(params.get("path") or "", str(params.get("delimiter") or ""))
        name = _checked_name(params, table)
        geometry = _geometry(params, table)
        layer = open_delimited(table, name, **{key: geometry.get(key, "") for key in GEOMETRY_KEYS})
        QgsProject.instance().addMapLayer(layer)
        result: dict[str, Any] = {**layer_reference(layer), "fields": list(layer.fields().names())}
        result.update(feature_count_block(layer))
        if geometry:
            result.update({"geometry": geometry_type_name(layer), "crs": crs_authid(layer)})
        else:
            result["geometry"] = None
        codes = table.text_codes()
        if codes:
            result["text_codes"] = codes
        return result


def _checked_name(params: dict[str, Any], table: DelimitedTable) -> str:
    name = str(params.get("name") or "").strip() or table.stem
    if QgsProject.instance().mapLayersByName(name):
        raise ValueError(f"A layer named '{name}' is already in the project. Give another name.")
    return name


def _geometry(params: dict[str, Any], table: DelimitedTable) -> dict[str, str]:
    """The geometry arguments to load with, checked against the file; empty for a plain table."""
    x_field = str(params.get("x_field") or "").strip()
    y_field = str(params.get("y_field") or "").strip()
    wkt_field = str(params.get("wkt_field") or "").strip()
    crs, geographic = normalised_crs(params.get("crs"))
    if wkt_field and (x_field or y_field):
        raise ValueError("Give either wkt_field or x_field with y_field, not both.")
    if bool(x_field) != bool(y_field):
        raise ValueError(f"x_field and y_field go together. {_columns(table)}")
    if params.get("table_only"):
        if x_field or wkt_field:
            raise ValueError("table_only loads no geometry; drop it or the coordinate columns.")
        return {}
    if not (x_field or wkt_field):
        guess = guess_coordinates(table)
        if not guess.found:
            return {}
        if not guess.crs and not crs:
            shown = guess.wkt_field or f"{guess.x_field}/{guess.y_field}"
            raise ValueError(
                f"Columns {shown} look like coordinates but are not longitude/latitude degrees. "
                "Pass crs with the projected system they were written in, or table_only=true."
            )
        x_field, y_field, wkt_field = guess.x_field, guess.y_field, guess.wkt_field
        if not crs:
            crs, geographic = normalised_crs(guess.crs)
    if wkt_field:
        return {"wkt_field": wkt_field, "crs": checked_wkt_crs(table, wkt_field, crs, geographic)}
    return {"x_field": x_field, "y_field": y_field, "crs": checked_xy_crs(table, x_field, y_field, crs, geographic)}


def normalised_crs(raw: Any) -> tuple[str, bool]:
    """The authority id of a CRS given as EPSG:4326, 4326, WGS84 or PROJ, and whether it is in degrees."""
    text = str(raw or "").strip()
    if not text:
        return "", False
    if text.isdigit():
        text = f"EPSG:{text}"
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        crs = QgsCoordinateReferenceSystem()
        crs.createFromUserInput(text)
    if not crs.isValid():
        raise ValueError(f"'{text}' is not a coordinate system. Use an identifier such as EPSG:4326.")
    authid = crs.authid()
    return (authid if isinstance(authid, str) and authid else text), bool(crs.isGeographic())


def _columns(table: DelimitedTable) -> str:
    return f"Available columns: {', '.join(table.header)}."
