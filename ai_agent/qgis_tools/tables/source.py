"""Delimited text layers and the join keys of project layers.

The URI is assembled with `QUrlQuery`, as the QGIS Data Source Manager does:
a hand-escaped `%3B` reaches the provider literally and splits every line on
three characters instead of one semicolon.
"""

from contextlib import suppress
from typing import Any

from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QUrl, QUrlQuery

from ai_agent.qgis_tools.common.layers import COUNTABLE_PROVIDERS, find_layer_by_name
from ai_agent.qgis_tools.common.paths import physical_path, same_path
from ai_agent.qgis_tools.tables.delimited import DelimitedTable
from ai_agent.qgis_tools.tables.keys import key_text

PROVIDER = "delimitedtext"
DUPLICATE_NAME = "{0} ({1})"


def delimited_uri(
    table: DelimitedTable, x_field: str = "", y_field: str = "", wkt_field: str = "", crs: str = ""
) -> str:
    """A delimitedtext URI; digit codes with leading zeros are pinned to text."""
    query = QUrlQuery()
    items = [
        ("type", "csv"),
        ("delimiter", "\\t" if table.delimiter == "\t" else table.delimiter),
        ("encoding", table.encoding),
        ("detectTypes", "yes"),
    ]
    if table.decimal_comma:
        items.append(("decimalPoint", ","))
    items.extend(("field", f"{column}:text") for column in table.text_codes())
    if wkt_field:
        items.extend([("wktField", wkt_field), ("crs", crs)])
    elif x_field and y_field:
        items.extend([("xField", x_field), ("yField", y_field), ("crs", crs)])
    else:
        items.append(("geomType", "none"))
    for key, value in items:
        query.addQueryItem(key, value)
    url = QUrl.fromLocalFile(table.path)
    url.setQuery(query)
    return bytes(url.toEncoded()).decode("utf-8")


def open_delimited(table: DelimitedTable, name: str, **geometry: str) -> QgsVectorLayer:
    """A valid layer over the file, not yet added to the project."""
    layer = QgsVectorLayer(delimited_uri(table, **geometry), name, PROVIDER)
    if not layer.isValid():
        reason = ""
        with suppress(Exception):
            reason = layer.error().summary()
        raise ValueError(f"QGIS could not read '{table.path}' as a table: {reason or 'the provider refused it'}.")
    return layer


def layer_for_file(path: str) -> QgsVectorLayer | None:
    """A vector layer already in the project that reads exactly this file."""
    for layer in QgsProject.instance().mapLayers().values():
        if isinstance(layer, QgsVectorLayer) and same_path(source_file(layer), path):
            return layer
    return None


def source_file(layer: Any) -> str:
    try:
        source = str(layer.source() or "")
    except Exception:
        return ""
    if source.startswith("file:"):
        return QUrl(source.split("?", 1)[0]).toLocalFile()
    return physical_path(source)


def free_layer_name(wanted: str) -> str:
    taken = {(layer.name() or "").strip() for layer in QgsProject.instance().mapLayers().values()}
    if wanted not in taken:
        return wanted
    number = 2
    while DUPLICATE_NAME.format(wanted, number) in taken:
        number += 1
    return DUPLICATE_NAME.format(wanted, number)


def require_vector_layer(reference: str, role: str) -> QgsVectorLayer:
    layer = find_layer_by_name(reference)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"The {role} '{layer.name()}' is not a vector layer or table; it has no attributes.")
    return layer


def require_field(layer: QgsVectorLayer, name: str, role: str) -> str:
    wanted = str(name or "").strip()
    names = list(layer.fields().names())
    if wanted not in names:
        raise ValueError(
            f"The {role} '{layer.name()}' has no field '{wanted}'. Available fields: {', '.join(names[:40])}."
        )
    return wanted


def layer_key_texts(layer: QgsVectorLayer, field: str) -> set[str] | None:
    """Distinct key texts of a local layer; None when reading them could stall on a remote source."""
    provider = ""
    with suppress(Exception):
        provider = str(layer.providerType() or "").lower()
    if provider not in COUNTABLE_PROVIDERS:
        return None
    try:
        values = layer.uniqueValues(layer.fields().indexFromName(field))
    except Exception:
        return None
    texts = {key_text(value) for value in values}
    return {text for text in texts if text is not None}
