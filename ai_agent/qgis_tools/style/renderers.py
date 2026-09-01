from contextlib import suppress
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer

from ai_agent.qgis_tools.common.renderers import (
    RENDERER_NAMES,
    class_attribute,
    get_renderer,
    renderer_type,
)
from ai_agent.qgis_tools.common.values import plain_value
from ai_agent.qgis_tools.style.symbols import symbol_info

MAX_CLASSES = 30
CATEGORY_FIELDS = (("value", "value"), ("label", "label"))
RANGE_FIELDS = (("min", "lowerValue"), ("max", "upperValue"), ("label", "label"))
RULE_FIELDS = (("filter", "filterExpression"), ("label", "label"))


def describe_vector_renderer(layer: QgsVectorLayer) -> dict[str, Any]:
    renderer = get_renderer(layer)
    kind = renderer_type(layer)
    info: dict[str, Any] = {"type": kind, "type_readable": RENDERER_NAMES.get(kind, kind)}
    if renderer is None:
        return info

    attribute = class_attribute(layer)
    if attribute:
        info["class_attribute"] = attribute

    for key, source, fields in _class_sources(renderer):
        described = _describe_classes(source, fields)
        if described is not None:
            info[key] = described
            return info

    with suppress(Exception):
        info["symbol"] = symbol_info(renderer.symbol())
    return info


def _class_sources(renderer: Any) -> Any:
    return (
        ("classes", lambda: renderer.categories(), CATEGORY_FIELDS),
        ("classes", lambda: renderer.ranges(), RANGE_FIELDS),
        ("rules", lambda: renderer.rootRule().children(), RULE_FIELDS),
    )


def _describe_classes(source, fields: tuple) -> list[dict[str, Any]] | None:
    try:
        items = list(source())
    except Exception:
        return None
    result = []
    for item in items[:MAX_CLASSES]:
        entry: dict[str, Any] = {}
        for key, getter in fields:
            with suppress(Exception):
                entry[key] = plain_value(getattr(item, getter)())
        with suppress(Exception):
            entry["symbol"] = symbol_info(item.symbol())
        result.append(entry)
    return result


def describe_raster_renderer(layer: QgsRasterLayer) -> dict[str, Any]:
    renderer = get_renderer(layer)
    info: dict[str, Any] = {"type": renderer_type(layer)}
    with suppress(Exception):
        info["bands"] = [int(band) for band in renderer.usesBands()]
    return info
