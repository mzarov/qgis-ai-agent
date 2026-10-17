from typing import Any

from qgis.core import QgsFeatureRequest

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, safe_feature_count
from ai_agent.qgis_tools.common.values import plain_value
from ai_agent.qgis_tools.sql.statement import SQL_PARAM, checked_sql, short_sql
from ai_agent.qgis_tools.sql.virtual import open_query, resolve_sources

MAX_ROWS = 200
# A cell is a value to read, not a document: a polygon's WKT would fill the model's window on its own.
MAX_TEXT_CHARS = 300
QUERY_LAYER_NAME = "query_sql"
TRUNCATED_NOTE = "Only the first {0} rows are shown. Aggregate, filter or ORDER BY ... LIMIT to see what matters."
GEOMETRY_NOTE = (
    "The rows have geometry; it is not sent. Select numbers from it (ST_Area, ST_X) "
    "or put the result on the map with create_sql_layer."
)
EMPTY_NOTE = "No rows. A computed column of an empty result may be missing from columns."


class QuerySqlTool(BaseTool):
    name = "query_sql"
    description = (
        "Answer a question with one SQL SELECT over the project's vector layers (SQLite with SpatiaLite "
        "functions): joins between layers, GROUP BY statistics, spatial joins such as points per polygon. "
        "Reads only; returns the columns and up to "
        f"{MAX_ROWS} rows with the total row count."
    )
    skill = "sql"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = [
        "A single SELECT or WITH ... SELECT statement; nothing that writes",
        "Only vector layers are tables",
    ]
    examples = [
        "How many schools are in each district?",
        "Total road length per district in km",
        "Average price per square metre by okrug, joining parcels and sales",
    ]
    params_schema = [SQL_PARAM]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Running SQL: {0}").format(short_sql(params.get("sql")) or "…")

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        return tr_n("%n row(s)", int(payload.get("row_count") or 0))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        sql = checked_sql(params.get("sql"))
        layer = open_query(sql, resolve_sources(sql), QUERY_LAYER_NAME)
        request = QgsFeatureRequest()
        request.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        request.setLimit(MAX_ROWS + 1)
        rows = [[cell(value) for value in feature.attributes()] for feature in layer.getFeatures(request)]
        result: dict[str, Any] = {"columns": list(layer.fields().names())}
        result.update(_counted(layer, rows))
        if _is_spatial(layer):
            result["geometry"] = geometry_type_name(layer)
            crs = crs_authid(layer)
            if crs:
                result["crs"] = crs
            result["geometry_note"] = GEOMETRY_NOTE
        return result


def cell(value: Any) -> Any:
    """A result value the model can read: plain JSON, long texts cut, binary data named by its size."""
    if isinstance(value, (bytes, bytearray)) or type(value).__name__ == "QByteArray":
        return f"<binary, {len(value)} bytes>"
    plain = plain_value(value)
    if isinstance(plain, str) and len(plain) > MAX_TEXT_CHARS:
        return plain[:MAX_TEXT_CHARS] + "…"
    return plain


def _counted(layer: Any, rows: list[list[Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": [], "row_count": 0, "note": EMPTY_NOTE}
    if len(rows) <= MAX_ROWS:
        return {"rows": rows, "row_count": len(rows)}
    # Past the cap the provider counts with one COUNT(*) over the query instead of rows read here.
    total = safe_feature_count(layer)
    counted: dict[str, Any] = {"rows": rows[:MAX_ROWS], "shown": MAX_ROWS, "note": TRUNCATED_NOTE.format(MAX_ROWS)}
    if total is not None and total > MAX_ROWS:
        counted["row_count"] = total
    else:
        counted["row_count"] = MAX_ROWS + 1
        counted["row_count_is_lower_bound"] = True
    return counted


def _is_spatial(layer: Any) -> bool:
    try:
        return bool(layer.isSpatial())
    except Exception:
        return False
