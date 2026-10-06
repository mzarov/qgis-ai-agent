"""The connectors as the settings page lists them: plain rows, so ui/ never touches the tool catalogue."""

from collections.abc import Iterable
from typing import Any

from ai_agent.config.connectors import disabled_connectors, set_disabled_connectors
from ai_agent.qgis_tools.data.connectors import CATEGORIES, CONNECTORS, Connector


def connector_rows() -> list[dict[str, Any]]:
    """Every connector with its texts, what it offers item by item, its hosts and licences, and whether it is on."""
    off = disabled_connectors()
    rows = []
    for connector in CONNECTORS:
        items = _items(connector)
        rows.append(
            {
                "id": connector.id,
                "title": connector.title,
                "category": connector.category,
                "summary": connector.summary,
                "description": connector.description,
                "examples": list(connector.examples),
                "monogram": connector.monogram,
                "items": items,
                "count": len(items),
                "hosts": list(connector.hosts),
                "licence": connector.licence,
                "enabled": connector.id not in off,
            }
        )
    return rows


def _items(connector: Connector) -> list[dict[str, Any]]:
    """One entry per layer of a web service, one per dataset otherwise; `kind` is the protocol or the dataset kind."""
    items: list[dict[str, Any]] = []
    for dataset in connector.datasets:
        if not dataset.layers:
            title = connector.labels.get(dataset.id, dataset.title)
            items.append({"title": title, "kind": dataset.kind, "zmax": 0})
            continue
        for layer in dataset.layers:
            items.append({"title": layer.title, "kind": layer.protocol or dataset.service, "zmax": layer.zmax})
    return items


def categories() -> tuple[str, ...]:
    return CATEGORIES


def save_enabled(enabled: Iterable[str]) -> None:
    """Store the switches: every connector not in `enabled` is turned off."""
    on = set(enabled)
    set_disabled_connectors(connector.id for connector in CONNECTORS if connector.id not in on)
