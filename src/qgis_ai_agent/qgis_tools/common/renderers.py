from qgis.core import QgsMapLayer

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
