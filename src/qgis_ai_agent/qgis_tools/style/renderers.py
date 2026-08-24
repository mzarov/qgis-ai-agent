from typing import Any

from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer

from qgis_ai_agent.qgis_tools.style.symbols import symbol_info

MAX_CLASSES = 30
RENDERER_NAMES = {
    "singleSymbol": "одиночный символ",
    "categorizedSymbol": "категории",
    "graduatedSymbol": "градации",
    "RuleRenderer": "по правилам",
    "nullSymbol": "без отрисовки",
    "pointCluster": "кластеры точек",
    "heatmapRenderer": "тепловая карта",
    "25dRenderer": "2.5D",
}


def get_renderer(layer: QgsMapLayer):
    try:
        return layer.renderer()
    except Exception:
        return None


def renderer_type(layer: QgsMapLayer) -> str:
    renderer = get_renderer(layer)
    if renderer is None:
        return ""
    try:
        return renderer.type() or ""
    except Exception:
        return ""


def class_attribute(layer: QgsMapLayer) -> str:
    renderer = get_renderer(layer)
    try:
        return renderer.classAttribute() or ""
    except Exception:
        return ""


def renderer_summary(layer: QgsMapLayer) -> str:
    kind = renderer_type(layer)
    if not kind:
        return ""
    readable = RENDERER_NAMES.get(kind, kind)
    attribute = class_attribute(layer)
    count = _class_count(layer)
    if attribute and count is not None:
        return f"{readable} по полю «{attribute}», классов: {count}"
    if attribute:
        return f"{readable} по полю «{attribute}»"
    return readable


def _class_count(layer: QgsMapLayer) -> int | None:
    renderer = get_renderer(layer)
    for getter in ("categories", "ranges"):
        try:
            return len(getattr(renderer, getter)())
        except Exception:
            continue
    return None


def describe_vector_renderer(layer: QgsVectorLayer) -> dict[str, Any]:
    renderer = get_renderer(layer)
    kind = renderer_type(layer)
    info: dict[str, Any] = {"type": kind, "type_ru": RENDERER_NAMES.get(kind, kind)}
    if renderer is None:
        return info

    attribute = class_attribute(layer)
    if attribute:
        info["class_attribute"] = attribute

    categories = _describe_categories(renderer)
    if categories is not None:
        info["classes"] = categories
        return info
    ranges = _describe_ranges(renderer)
    if ranges is not None:
        info["classes"] = ranges
        return info
    rules = _describe_rules(renderer)
    if rules is not None:
        info["rules"] = rules
        return info

    try:
        info["symbol"] = symbol_info(renderer.symbol())
    except Exception:
        pass
    return info


def _describe_categories(renderer) -> list[dict[str, Any]] | None:
    try:
        categories = renderer.categories()
    except Exception:
        return None
    result = []
    for category in list(categories)[:MAX_CLASSES]:
        entry: dict[str, Any] = {}
        for key, getter in (("value", "value"), ("label", "label")):
            try:
                entry[key] = _plain(getattr(category, getter)())
            except Exception:
                continue
        try:
            entry["symbol"] = symbol_info(category.symbol())
        except Exception:
            pass
        result.append(entry)
    return result


def _describe_ranges(renderer) -> list[dict[str, Any]] | None:
    try:
        ranges = renderer.ranges()
    except Exception:
        return None
    result = []
    for item in list(ranges)[:MAX_CLASSES]:
        entry: dict[str, Any] = {}
        for key, getter in (("min", "lowerValue"), ("max", "upperValue"), ("label", "label")):
            try:
                entry[key] = _plain(getattr(item, getter)())
            except Exception:
                continue
        try:
            entry["symbol"] = symbol_info(item.symbol())
        except Exception:
            pass
        result.append(entry)
    return result


def _describe_rules(renderer) -> list[dict[str, Any]] | None:
    try:
        children = renderer.rootRule().children()
    except Exception:
        return None
    result = []
    for rule in list(children)[:MAX_CLASSES]:
        entry: dict[str, Any] = {}
        for key, getter in (("filter", "filterExpression"), ("label", "label")):
            try:
                entry[key] = _plain(getattr(rule, getter)())
            except Exception:
                continue
        try:
            entry["symbol"] = symbol_info(rule.symbol())
        except Exception:
            pass
        result.append(entry)
    return result


def describe_raster_renderer(layer: QgsRasterLayer) -> dict[str, Any]:
    renderer = get_renderer(layer)
    info: dict[str, Any] = {"type": renderer_type(layer)}
    try:
        info["bands"] = [int(band) for band in renderer.usesBands()]
    except Exception:
        pass
    return info


def _plain(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
