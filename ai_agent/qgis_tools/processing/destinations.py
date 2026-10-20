import os
import re
from typing import Any

from qgis.core import QgsDataSourceUri, QgsProviderRegistry

from ai_agent.qgis_tools.common.paths import check_overwrite

TEMPORARY_OUTPUT = "TEMPORARY_OUTPUT"
MEMORY_PREFIX = "memory:"
OGR_PROVIDER = "ogr"
# Processing writes "key://uri", or "key:uri" with a key of three or more characters, through that provider.
PROVIDER_URI = re.compile(r"(\w+?)://(.+)|(.{3,}?):(.*)", re.DOTALL)
TABLE_TAKEN_ERROR = (
    "Table '{table}' already exists in '{database}'. Refusing to replace it unless overwrite_outputs=true "
    "is explicitly approved. Write to another table, or ask the user before replacing it."
)
UNLISTED_ERROR = (
    "Could not list the tables of '{database}', so writing table '{table}' into it might replace one. "
    "Write to a new file, or ask the user before setting overwrite_outputs=true."
)


def destination_values(parameters: dict[str, Any], destination_names: list[str] | None = None) -> list[str]:
    selected = {str(name) for name in destination_names or []}
    values = []
    for name, value in parameters.items():
        key = str(name)
        upper = key.upper()
        if key not in selected and "OUTPUT" not in upper and "DESTINATION" not in upper:
            continue
        if not isinstance(value, str):
            continue
        destination = value.strip()
        if not destination or destination.upper() == TEMPORARY_OUTPUT or destination.startswith(MEMORY_PREFIX):
            continue
        values.append(destination)
    return values


def check_destinations(parameters: dict[str, Any], overwrite: bool, destination_names: list[str] | None = None) -> None:
    for value in destination_values(parameters, destination_names):
        provider, uri = provider_destination(value)
        if not provider:
            check_overwrite(value, overwrite)
        elif provider == OGR_PROVIDER:
            _check_ogr_table(uri, overwrite)


def database_destinations(parameters: dict[str, Any], destination_names: list[str] | None = None) -> list[str]:
    return [
        value
        for value in destination_values(parameters, destination_names)
        if provider_destination(value)[0] not in ("", OGR_PROVIDER)
    ]


def provider_destination(value: str) -> tuple[str, str]:
    match = PROVIDER_URI.fullmatch(value)
    if match is None:
        return "", value
    if match.group(1):
        return match.group(1).lower(), match.group(2)
    return match.group(3).lower(), match.group(4)


def _check_ogr_table(uri: str, overwrite: bool) -> None:
    source = QgsDataSourceUri(uri)
    database, table = str(source.database() or ""), str(source.table() or "")
    if not database:
        check_overwrite(uri, overwrite)
        return
    if overwrite or not os.path.lexists(database):
        return
    if not table:
        check_overwrite(database, overwrite)
        return
    tables = _table_names(database)
    if tables is None:
        raise ValueError(UNLISTED_ERROR.format(database=database, table=table))
    if table.casefold() in tables:
        raise ValueError(TABLE_TAKEN_ERROR.format(database=database, table=table))


def _table_names(database: str) -> set[str] | None:
    try:
        details = QgsProviderRegistry.instance().querySublayers(database)
    except Exception:
        return None
    names = {str(detail.name()).casefold() for detail in details if detail.name()}
    return names or None
