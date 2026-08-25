from typing import Any

from qgis_ai_agent.qgis_tools.style.properties import PropertySet

SHOWN_IN_SUMMARY = 4


def properties_of(params: dict[str, Any], subject: str) -> dict[str, Any]:
    properties = params.get("properties")
    if properties is None:
        return {}
    if not isinstance(properties, dict):
        raise ValueError(
            f"Свойства ({subject}) передаются объектом пар ключ-значение, "
            "а не строкой или списком. Список ключей — describe_style_options."
        )
    return dict(properties)


def shown(properties: dict[str, Any], known: PropertySet) -> str:
    pairs = [f"{key}={value}" for key, value in properties.items() if key in known.by_name]
    if not pairs:
        return "по умолчанию"
    if len(pairs) <= SHOWN_IN_SUMMARY:
        return ", ".join(pairs)
    head = ", ".join(pairs[:SHOWN_IN_SUMMARY])
    return f"{head} и ещё {len(pairs) - SHOWN_IN_SUMMARY}"
