from typing import Any

from qgis.core import QgsProviderRegistry

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool

DB_PROVIDER = "postgres"
NO_CONNECTIONS_NOTE = (
    "No saved PostGIS connections. The user creates one in the QGIS Browser "
    "panel (PostgreSQL → New Connection); the plugin cannot store credentials."
)


def db_connections() -> dict[str, Any]:
    metadata = QgsProviderRegistry.instance().providerMetadata(DB_PROVIDER)
    if metadata is None:
        raise ValueError("The PostgreSQL provider is not available in this QGIS build.")
    found = metadata.connections()
    return dict(found) if found else {}


def require_connection(name: str) -> Any:
    wanted = (name or "").strip()
    known = db_connections()
    if wanted in known:
        return known[wanted]
    available = ", ".join(f"'{title}'" for title in sorted(known)) or "none saved"
    raise ValueError(f"No connection named '{wanted}'. Available: {available}.")


class ListDbConnectionsTool(BaseTool):
    name = "list_db_connections"
    description = (
        "List the PostGIS database connections saved in this QGIS profile. "
        "Call it before browsing tables or loading a database layer."
    )
    skill = "project"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    examples = ["Which databases can I connect to?", "Load the roads table from PostGIS"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the saved database connections.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        names = sorted(db_connections())
        if not names:
            return {"connections": [], "note": NO_CONNECTIONS_NOTE}
        return {"connections": names, "count": len(names)}
