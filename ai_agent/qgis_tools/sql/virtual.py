"""A checked SELECT turned into a QGIS virtual layer over the project's layers, each bound by its id.

The virtual provider can find tables by layer name itself, but with two layers
of one name it silently takes either. Every name the SQL uses is resolved here
instead and handed over as `layer_ref` (id and alias), so a duplicate name is
refused with the ids to choose from, and a planned query keeps reading the same
layers after a rename.
"""

import re
from contextlib import suppress
from typing import Any

from qgis.core import QgsProject, QgsVectorLayer, QgsVirtualLayerDefinition

from ai_agent.qgis_tools.common.layers import layer_identifier
from ai_agent.qgis_tools.sql.statement import identifiers, statement_tokens

PROVIDER = "virtual"
# Private: queued calls keep the layers their SQL was resolved to, hidden from the model's view of the plan.
SOURCES_KEY = "_sql_sources"
ALIAS = "alias"
LAYER_ID = "id"
# The provider wraps the query in statements of its own and repeats the SQL in its error; the reason follows these.
WRAPPER_MARKERS = ("_tview AS {sql}: ", "table_info(_tview): ")
SQLITE_CODE = re.compile(r"^\d+ - ")
MISSING_TABLE_SIGNS = ("not found", "no such table")
FIX_HINT = 'Fix the SQL (SQLite with SpatiaLite functions; each layer\'s geometry column is "geometry") and call again.'
TABLES_HINT = "Tables are the project's vector layers, named in double quotes: {0}."
NO_TABLES = "the project has no vector layers"
AMBIGUOUS_ERROR = (
    "Layer name '{0}' is ambiguous: {1} project layers have it ({2}). "
    'Name one by its id in double quotes instead, e.g. FROM "{3}".'
)
GONE_ERROR = "Layer '{0}', which the query reads, is no longer in the project. Plan the query again."


def resolve_sources(sql: str) -> list[dict[str, str]]:
    """Each project vector layer the SQL names, as {alias, id}: the alias is the name as the SQL writes it.

    Names are matched as `find_layer_by_name` does: a layer id first, then the
    exact name, then the name in any letter case. Names that are no layer are
    columns, aliases or tables the provider will report as missing.
    """
    layers = _vector_layers()
    sources: list[dict[str, str]] = []
    taken: set[str] = set()
    for name in identifiers(statement_tokens(sql)):
        # SQLite table names ignore letter case: one table per spelling would collide.
        if name.casefold() in taken:
            continue
        layer = _named_layer(name, layers)
        if layer is None:
            continue
        taken.add(name.casefold())
        sources.append({ALIAS: name, LAYER_ID: layer_identifier(layer)})
    return sources


def planned_sources(params: dict[str, Any]) -> list[dict[str, str]]:
    """The sources a queued call was resolved to, each still in the project; resolved afresh when absent."""
    planned = params.get(SOURCES_KEY)
    if not isinstance(planned, list):
        return resolve_sources(str(params.get("sql") or ""))
    try:
        present = QgsProject.instance().mapLayers()
    except Exception:
        present = {}
    sources = []
    for source in planned:
        if not isinstance(source, dict):
            continue
        alias, identifier = str(source.get(ALIAS) or ""), str(source.get(LAYER_ID) or "")
        if identifier not in present:
            raise ValueError(GONE_ERROR.format(alias or identifier))
        sources.append({ALIAS: alias, LAYER_ID: identifier})
    return sources


def open_query(sql: str, sources: list[dict[str, str]], name: str) -> QgsVectorLayer:
    """A valid virtual layer for the query, not added to the project. Raises ValueError with the provider's reason."""
    definition = QgsVirtualLayerDefinition()
    for source in sources:
        definition.addSource(source[ALIAS], source[LAYER_ID])
    definition.setQuery(sql)
    layer = QgsVectorLayer(definition.toString(), name, PROVIDER)
    if not layer.isValid():
        raise ValueError(query_error(layer, sql))
    return layer


def query_error(layer: Any, sql: str) -> str:
    """The provider's reason the query failed, without the wrapper statement it repeats, and how to go on."""
    reason = _provider_reason(layer, sql) or "QGIS gave no reason"
    lowered = reason.lower()
    if any(sign in lowered for sign in MISSING_TABLE_SIGNS):
        names = ", ".join(f'"{(item.name() or "").strip()}"' for item in _vector_layers()) or NO_TABLES
        return f"The query failed: {reason}. {TABLES_HINT.format(names)}"
    return f"The query failed: {reason}. {FIX_HINT}"


def _provider_reason(layer: Any, sql: str) -> str:
    text = ""
    with suppress(Exception):
        provider = layer.dataProvider()
        if provider is not None:
            text = str(provider.error().summary() or "")
    if not text:
        with suppress(Exception):
            text = str(layer.error().summary() or "")
    for template in WRAPPER_MARKERS:
        marker = template.format(sql=sql)
        position = text.find(marker)
        if position >= 0:
            text = text[position + len(marker) :]
            break
    return SQLITE_CODE.sub("", text.strip()).rstrip(".!")


def _vector_layers() -> list[QgsVectorLayer]:
    try:
        layers = QgsProject.instance().mapLayers().values()
    except Exception:
        return []
    return [layer for layer in layers if isinstance(layer, QgsVectorLayer)]


def _named_layer(name: str, layers: list[QgsVectorLayer]) -> QgsVectorLayer | None:
    for layer in layers:
        if layer_identifier(layer) == name:
            return layer
    exact = [layer for layer in layers if (layer.name() or "").strip() == name]
    if not exact:
        folded = name.casefold()
        exact = [layer for layer in layers if (layer.name() or "").strip().casefold() == folded]
    if len(exact) > 1:
        choices = ", ".join(f"'{(layer.name() or '').strip()}' [id={layer_identifier(layer)}]" for layer in exact)
        raise ValueError(AMBIGUOUS_ERROR.format(name, len(exact), choices, layer_identifier(exact[0])))
    return exact[0] if exact else None
