from typing import Any

from qgis.core import QgsMapLayer, QgsProject, QgsRasterLayer, QgsVectorLayer

# Точность округления координат в градусах/метрах для ответов модели.
COORD_PRECISION = 6


def geometry_type_name(layer: QgsMapLayer) -> str:
    """Возвращает читаемое имя типа геометрии векторного слоя."""
    if not isinstance(layer, QgsVectorLayer):
        return ""
    try:
        gtype = str(layer.geometryType()).lower()
    except Exception:
        return "вектор"
    if "point" in gtype:
        return "точки"
    if "line" in gtype:
        return "линии"
    if "polygon" in gtype:
        return "полигоны"
    return "вектор"


def layer_kind(layer: QgsMapLayer) -> str:
    """Возвращает вид слоя: vector, raster или other."""
    if isinstance(layer, QgsVectorLayer):
        return "vector"
    if isinstance(layer, QgsRasterLayer):
        return "raster"
    return "other"


def crs_authid(layer: QgsMapLayer) -> str:
    """Возвращает код системы координат слоя, например EPSG:4326."""
    try:
        return layer.crs().authid() or ""
    except Exception:
        return ""


def crs_is_geographic(layer: QgsMapLayer) -> bool:
    """
    Географическая ли CRS слоя. Важно для обработки: в такой CRS расстояния
    измеряются в градусах, и буфер «500 метров» без перепроецирования не построить.
    """
    try:
        return bool(layer.crs().isGeographic())
    except Exception:
        return False


def crs_units(layer: QgsMapLayer) -> str:
    """Единицы измерения CRS слоя человекочитаемо."""
    return "градусы" if crs_is_geographic(layer) else "метры или иные линейные единицы"


def suggest_metric_crs(layer: QgsMapLayer) -> str:
    """
    Подбирает метрическую CRS для перепроецирования слоя.
    Сначала пробует CRS проекта — если она метрическая, результат ляжет в общую
    систему координат. Иначе считает зону UTM по центру охвата слоя.
    """
    try:
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid() and not project_crs.isGeographic():
            authid = project_crs.authid()
            if authid:
                return authid
    except Exception:
        pass
    return _utm_authid(layer)


def _utm_authid(layer: QgsMapLayer) -> str:
    """Код зоны UTM по центру охвата слоя, с откатом на EPSG:3857."""
    try:
        extent = layer.extent()
        longitude = (float(extent.xMinimum()) + float(extent.xMaximum())) / 2.0
        latitude = (float(extent.yMinimum()) + float(extent.yMaximum())) / 2.0
    except Exception:
        return "EPSG:3857"
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        return "EPSG:3857"
    zone = max(1, min(60, int((longitude + 180.0) / 6.0) + 1))
    return f"EPSG:{(32600 if latitude >= 0 else 32700) + zone}"


def extent_dict(rectangle) -> dict[str, float] | None:
    """Переводит QgsRectangle в словарь с округлением."""
    if rectangle is None:
        return None
    try:
        if rectangle.isEmpty():
            return None
        return {
            "xmin": round(float(rectangle.xMinimum()), COORD_PRECISION),
            "ymin": round(float(rectangle.yMinimum()), COORD_PRECISION),
            "xmax": round(float(rectangle.xMaximum()), COORD_PRECISION),
            "ymax": round(float(rectangle.yMaximum()), COORD_PRECISION),
        }
    except Exception:
        return None


def describe_layer_brief(layer: QgsMapLayer) -> dict[str, Any]:
    """Краткая карточка слоя для списка: без полей и без extent."""
    kind = layer_kind(layer)
    brief: dict[str, Any] = {
        "name": (layer.name() or "Без имени").strip(),
        "kind": kind,
        "crs": crs_authid(layer),
        "crs_is_geographic": crs_is_geographic(layer),
    }
    if kind == "vector":
        brief["geometry"] = geometry_type_name(layer)
        try:
            brief["feature_count"] = int(layer.featureCount())
        except Exception:
            pass
    return brief


def find_layer_by_name(name: str) -> QgsMapLayer:
    """Находит слой по имени или выбрасывает ValueError со списком доступных."""
    wanted = (name or "").strip()
    project = QgsProject.instance()
    if wanted:
        matches = project.mapLayersByName(wanted)
        if matches:
            return matches[0]
        # Запасной вариант: регистронезависимое сравнение.
        lowered = wanted.lower()
        for layer in project.mapLayers().values():
            if (layer.name() or "").strip().lower() == lowered:
                return layer
    available = [(layer.name() or "").strip() for layer in project.mapLayers().values()]
    hint = ", ".join(available) if available else "в проекте нет слоёв"
    raise ValueError(f"Слой не найден: «{wanted}». Доступные слои: {hint}.")
