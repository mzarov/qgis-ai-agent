"""The connectors as the settings page lists them: plain rows, so ui/ never touches the tool catalogue."""

from collections.abc import Iterable
from typing import Any

from ai_agent.config.connectors import disabled_connectors, set_disabled_connectors
from ai_agent.qgis_tools.data.catalogue import BY_ID
from ai_agent.qgis_tools.data.connectors import CATEGORIES, CONNECTORS


def connector_rows() -> list[dict[str, Any]]:
    """Every connector with its category, summary, number of datasets or layers, and whether it is on."""
    off = disabled_connectors()
    rows = []
    for connector in CONNECTORS:
        count = sum(max(1, len(BY_ID[item].layers)) for item in connector.datasets if item in BY_ID)
        rows.append(
            {
                "id": connector.id,
                "title": connector.title,
                "category": connector.category,
                "summary": connector.summary,
                "count": count,
                "hosts": list(connector.hosts),
                "enabled": connector.id not in off,
            }
        )
    return rows


def categories() -> tuple[str, ...]:
    return CATEGORIES


def save_enabled(enabled: Iterable[str]) -> None:
    """Store the switches: every connector not in `enabled` is turned off."""
    on = set(enabled)
    set_disabled_connectors(connector.id for connector in CONNECTORS if connector.id not in on)
