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
