"""Everything a join needs, checked once and used by both prepare and execute."""

from dataclasses import dataclass
from typing import Any

from qgis.core import QgsVectorLayer, QgsVectorLayerJoinInfo

from ai_agent.qgis_tools.common.layers import find_layer_by_id, layer_identifier
from ai_agent.qgis_tools.tables.delimited import (
    SCAN_BYTES,
    DelimitedTable,
    checked_path,
    looks_like_file,
    read_table,
)
from ai_agent.qgis_tools.tables.keys import file_key_texts, match_report
from ai_agent.qgis_tools.tables.source import (
    layer_for_file,
    layer_key_texts,
    require_field,
    require_vector_layer,
)

TABLE_ID = {
    "name": "table_id",
    "type": "string",
    "description": "Stable id of the table layer from list_layers; required when table names are duplicated",
    "required": False,
}


@dataclass
class JoinPlan:
    target: QgsVectorLayer
    layer_field: str
    table_field: str
    table_name: str
    prefix: str
    subset: list[str] | None
    joined_fields: list[str]
    table_layer: QgsVectorLayer | None = None
    table_file: DelimitedTable | None = None

    def match(self) -> dict[str, Any] | None:
        """The predicted match of distinct keys; None when a side is too costly to read."""
        target_keys = layer_key_texts(self.target, self.layer_field)
        table_keys = self._table_keys()
        if target_keys is None or table_keys is None:
            return None
        return match_report(target_keys, table_keys)

    def join_info(self, table_layer: QgsVectorLayer) -> QgsVectorLayerJoinInfo:
        info = QgsVectorLayerJoinInfo()
        info.setJoinLayer(table_layer)
        info.setJoinFieldName(self.table_field)
        info.setTargetFieldName(self.layer_field)
        # The cache is what the QGIS join dialog uses by default, and it fixes
        # the comparison to key text — the one `keys.py` predicts.
        info.setUsingMemoryCache(True)
        info.setPrefix(self.prefix)
        if self.subset:
            info.setJoinFieldNamesSubset(self.subset)
        return info

    def _table_keys(self) -> set[str] | None:
        if self.table_layer is not None:
            return layer_key_texts(self.table_layer, self.table_field)
        table = self.table_file
        if table is None or not table.complete:
            return None
        kind = table.column_type(self.table_field)
        return file_key_texts(table.values(self.table_field, strip=False), kind, table.decimal_comma)


def plan_join(params: dict[str, Any]) -> JoinPlan:
    target = target_layer(params)
    layer_field = require_field(target, params.get("layer_field") or "", "layer")
    reference = str(params.get("table") or "").strip()
    if not reference:
        raise ValueError("No table was given: name a project layer or a path to a CSV file.")
    source = _table_source(reference, str(params.get("table_id") or "").strip())
    table_layer = source if isinstance(source, QgsVectorLayer) else None
    table_file = source if isinstance(source, DelimitedTable) else None
    if table_layer is not None:
        if layer_identifier(table_layer) == layer_identifier(target):
            raise ValueError("A layer cannot be joined to itself.")
        table_name = (table_layer.name() or "").strip()
        available = list(table_layer.fields().names())
        table_field = require_field(table_layer, params.get("table_field") or "", "table")
        _refuse_second_join(target, table_layer)
    else:
        table_name, available = source.stem, list(source.header)
        table_field = str(params.get("table_field") or "").strip()
        source.require_columns([table_field])
    subset = _subset(params.get("fields"), available, table_field)
    raw_prefix = params.get("prefix")
    prefix = f"{table_name}_" if raw_prefix is None else str(raw_prefix)
    names = subset or [name for name in available if name != table_field]
    joined = [prefix + name for name in names]
    clashes = sorted(set(joined) & set(target.fields().names()))
    if clashes:
        raise ValueError(
            f"Joined fields would repeat names already in '{target.name()}': {', '.join(clashes)}. "
            "Give a prefix, or a fields subset without them."
        )
    return JoinPlan(target, layer_field, table_field, table_name, prefix, subset, joined, table_layer, table_file)


def target_layer(params: dict[str, Any]) -> QgsVectorLayer:
    layer_id = str(params.get("layer_id") or "").strip()
    if not layer_id:
        return require_vector_layer(params.get("layer_name") or "", "layer")
    layer = find_layer_by_id(layer_id)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer; joins need attributes.")
    return layer


def _table_source(reference: str, table_id: str) -> QgsVectorLayer | DelimitedTable:
    """A project layer, or a file not loaded yet; a file already in the project is its layer.

    A pinned id wins, so a join planned against one layer never lands on a namesake at apply time.
    """
    if table_id:
        layer = find_layer_by_id(table_id)
        named = looks_like_file(reference) or (layer.name() or "").strip().casefold() == reference.casefold()
        if not isinstance(layer, QgsVectorLayer) or not named:
            raise ValueError(f"table '{reference}' and table_id '{table_id}' identify different layers.")
        return layer
    if not looks_like_file(reference):
        return require_vector_layer(reference, "table")
    path = checked_path(reference)
    return layer_for_file(path) or read_table(path, limit=SCAN_BYTES)


def _refuse_second_join(target: QgsVectorLayer, table_layer: QgsVectorLayer) -> None:
    table_id = layer_identifier(table_layer)
    for join in target.vectorJoins():
        if join.joinLayerId() == table_id:
            raise ValueError(
                f"'{table_layer.name()}' is already joined to '{target.name()}'. "
                "Call remove_join first to join it on other keys."
            )


def _subset(raw: Any, available: list[str], key: str) -> list[str] | None:
    if raw is None or raw == []:
        return None
    if not isinstance(raw, list):
        raise ValueError("fields must be a list of table column names.")
    wanted = [str(name).strip() for name in raw if str(name).strip() and str(name).strip() != key]
    missing = [name for name in wanted if name not in available]
    if missing:
        raise ValueError(f"The table has no field {', '.join(missing)}. Available fields: {', '.join(available)}.")
    return wanted or None
