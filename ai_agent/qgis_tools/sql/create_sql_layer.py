from typing import Any

from qgis.core import QgsProject

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import crs_authid, feature_count_block, geometry_type_name, layer_reference
from ai_agent.qgis_tools.sql.statement import SQL_PARAM, checked_sql, short_sql
from ai_agent.qgis_tools.sql.virtual import SOURCES_KEY, open_query, planned_sources, resolve_sources

LIVE_NOTE = "A virtual layer: it runs the query again whenever it is drawn, so it follows edits of the layers it reads."
NAME_TAKEN_ERROR = "A layer named '{0}' is already in the project. Give another name."
NO_NAME_ERROR = "name is empty. Give the new layer a name."


class CreateSqlLayerTool(BaseTool):
    name = "create_sql_layer"
    description = (
        "Add the result of one SQL SELECT over the project's layers as a new virtual layer: it stays live "
        "like a view, so later edits of the source layers show up in it. The first geometry column of "
        "the result becomes the layer's geometry; without one it is a plain table."
    )
    skill = "sql"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "A single SELECT or WITH ... SELECT statement that runs without error",
        "The name must not be taken by another layer",
    ]
    examples = ["Make a layer of the districts with their school counts", "Keep the buffered stations as a layer"]
    params_schema = [
        SQL_PARAM,
        {"name": "name", "type": "string", "description": "Name of the new layer", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        sql = checked_sql(params.get("sql"))
        name = _free_name(params.get("name"))
        sources = resolve_sources(sql)
        # Built once and dropped: the provider checks the SQL and its tables now, while the model can still fix them.
        open_query(sql, sources, name)
        return {**params, "name": name, SOURCES_KEY: sources}

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("name") or "").strip()
        return tr("Adding layer '{0}' from SQL: {1}").format(name, short_sql(params.get("sql")) or "…")

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        count = payload.get("feature_count")
        return tr_n("%n feature(s)", count) if isinstance(count, int) else ""

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        sql = checked_sql(params.get("sql"))
        name = _free_name(params.get("name"))
        layer = open_query(sql, planned_sources(params), name)
        QgsProject.instance().addMapLayer(layer)
        result: dict[str, Any] = {**layer_reference(layer), "fields": list(layer.fields().names())}
        result.update(feature_count_block(layer))
        spatial = geometry_type_name(layer) if layer.isSpatial() else ""
        result["geometry"] = spatial or None
        if spatial:
            result["crs"] = crs_authid(layer)
        result["note"] = LIVE_NOTE
        return result

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        # The step's fact is one layer: in the project under the asked name, and valid, so its query runs.
        identifier = str(payload.get("layer_id") or "")
        layer = QgsProject.instance().mapLayer(identifier) if identifier else None
        if layer is None:
            return False
        return bool(layer.isValid()) and (layer.name() or "").strip() == str(params.get("name") or "").strip()


def _free_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValueError(NO_NAME_ERROR)
    if QgsProject.instance().mapLayersByName(name):
        raise ValueError(NAME_TAKEN_ERROR.format(name))
    return name
