from contextlib import suppress
from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from ai_agent.qgis_tools.project.list_db_connections import require_connection

MAX_TABLES = 200


class ListDbTablesTool(BaseTool):
    name = "list_db_tables"
    description = (
        "List the tables of a saved PostGIS connection: schema, table name and "
        "geometry column. Call it before add_db_layer to get the exact names."
    )
    skill = "project"
    safety = SAFETY_READ
    constraints = ["The connection must exist in the QGIS profile (see list_db_connections)"]
    examples = ["What tables does the production database have?"]
    params_schema = [
        {
            "name": "connection",
            "type": "string",
            "description": "Connection name exactly as in list_db_connections",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = (params.get("connection") or "").strip()
        return tr("Reading the tables of connection '{0}'.").format(name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        connection = require_connection(params.get("connection") or "")
        described = [_described(table) for table in connection.tables()]
        result: dict[str, Any] = {"tables": described[:MAX_TABLES], "count": len(described)}
        if len(described) > MAX_TABLES:
            result["note"] = f"showing the first {MAX_TABLES} tables of {len(described)}"
        return result


def _described(table: Any) -> dict[str, Any]:
    described: dict[str, Any] = {}
    for key, getter in (("schema", "schema"), ("table", "tableName"), ("geometry_column", "geometryColumn")):
        with suppress(Exception):
            value = getattr(table, getter)()
            if value:
                described[key] = str(value)
    return described
