from qgis.core import QgsProject


def _geometry_type_name(layer) -> str:
    if not hasattr(layer, "geometryType"):
        return "вектор"
    try:
        gtype = layer.geometryType()
        gt_text = str(gtype).lower()
        if "point" in gt_text:
            return "точки"
        if "line" in gt_text:
            return "линии"
        if "polygon" in gt_text:
            return "полигоны"
    except Exception:
        pass
    return "вектор"


def get_project_context() -> str:
    """Возвращает строку с контекстом проекта: макеты, слои и типы геометрии."""
    project = QgsProject.instance()
    parts = []

    manager = project.layoutManager()
    layouts = [lay.name() for lay in manager.layouts()]
    if layouts:
        parts.append("Макеты в проекте: " + ", ".join(layouts) + ".")
    else:
        parts.append("Макеты в проекте: нет.")

    layer_parts = []
    for layer in project.mapLayers().values():
        name = (layer.name() or "Без имени").strip()
        if "raster" in str(type(layer).__name__).lower():
            layer_parts.append(f"{name} (растр)")
        else:
            geom = _geometry_type_name(layer)
            layer_parts.append(f"{name} ({geom})")
    if layer_parts:
        parts.append("Слои: " + ", ".join(layer_parts) + ".")
    else:
        parts.append("Слои: нет.")

    return " ".join(parts)
