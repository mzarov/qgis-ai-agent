from typing import Any

from qgis.core import QgsVectorLayer

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import crs_authid, geometry_type_name, safe_feature_count
from qgis_ai_agent.qgis_tools.project.list_db_connections import require_connection
from qgis_ai_agent.qgis_tools.project.tree import layer_names, project

DB_PROVIDER = "postgres"


class AddDbLayerTool(BaseTool):
    name = "add_db_layer"
    description = (
        "Load a table from a saved PostGIS connection into the project as a "
        "vector layer. Get the exact schema and table names from list_db_tables "
        "first."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "The connection must exist in the QGIS profile",
        "Schema and table names are case sensitive",
    ]
    examples = ["Load public.roads from the production database"]
    params_schema = [
        {
            "name": "connection",
            "type": "string",
            "description": "Connection name exactly as in list_db_connections",
            "required": True,
        },
        {
            "name": "schema",
            "type": "string",
            "description": "Schema name, usually public",
            "required": True,
        },
        {
            "name": "table",
            "type": "string",
            "description": "Table name exactly as in list_db_tables",
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Layer name in the project. Defaults to the table name.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        require_connection(params.get("connection") or "")
        title = _wanted_name(params)
        if title in layer_names():
            raise ValueError(f"A layer named '{title}' is already in the project. Give another name.")
        prepared = dict(params)
        prepared["name"] = title
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        schema = (params.get("schema") or "").strip()
        table = (params.get("table") or "").strip()
        return tr("Loading table {0}.{1} from the database.").format(schema, table)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        connection = require_connection(params.get("connection") or "")
        schema = (params.get("schema") or "").strip()
        table = (params.get("table") or "").strip()
        uri = connection.tableUri(schema, table)
        layer = QgsVectorLayer(uri, _wanted_name(params), DB_PROVIDER)
        if not layer.isValid():
            raise ValueError(
                f"QGIS could not open {schema}.{table}: check the names with "
                "list_db_tables and that the database is reachable."
            )
        project().addMapLayer(layer)
        return {
            "name": layer.name(),
            "crs": crs_authid(layer),
            "geometry": geometry_type_name(layer),
            "feature_count": safe_feature_count(layer),
        }


def _wanted_name(params: dict[str, Any]) -> str:
    given = (params.get("name") or "").strip()
    return given or (params.get("table") or "").strip() or "database layer"
