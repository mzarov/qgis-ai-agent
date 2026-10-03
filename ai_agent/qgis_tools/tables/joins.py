"""Reading the joins a layer already has: listing them and finding one to remove."""

from typing import Any

from ai_agent.qgis_tools.tables.keys import match_report
from ai_agent.qgis_tools.tables.source import layer_key_texts


def describe_join(target: Any, join: Any) -> dict[str, Any]:
    """One join as the model reads it, with the key match measured when that is cheap."""
    table = join.joinLayer()
    described: dict[str, Any] = {
        "table": table.name() if table is not None else join.joinLayerId(),
        "table_id": join.joinLayerId(),
        "layer_field": join.targetFieldName(),
        "table_field": join.joinFieldName(),
    }
    if table is None:
        described["note"] = "The joined table is no longer in the project; the joined fields are empty."
        return described
    described["joined_fields"] = joined_field_names(join, table)
    target_keys = layer_key_texts(target, join.targetFieldName())
    table_keys = layer_key_texts(table, join.joinFieldName())
    if target_keys is not None and table_keys is not None:
        described["match"] = match_report(target_keys, table_keys)
    return described


def joined_field_names(join: Any, table: Any) -> list[str]:
    subset = join.joinFieldNamesSubset()
    key = join.joinFieldName()
    return [
        join.prefixedFieldName(field)
        for field in table.fields()
        if field.name() != key and (subset is None or field.name() in subset)
    ]


def find_join(target: Any, reference: str) -> Any:
    """The join of `target` whose table has this name or id; the error lists the joined tables."""
    wanted = str(reference or "").strip()
    joins = list(target.vectorJoins())
    for join in joins:
        table = join.joinLayer()
        if wanted in (join.joinLayerId(), table.name() if table is not None else ""):
            return join
    joined = ", ".join(_table_label(join) for join in joins) or "none"
    raise ValueError(f"'{target.name()}' has no join with '{wanted}'. Joined tables: {joined}.")


def _table_label(join: Any) -> str:
    table = join.joinLayer()
    return f"'{table.name()}'" if table is not None else f"[id={join.joinLayerId()}]"
