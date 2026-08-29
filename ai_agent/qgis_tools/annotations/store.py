from typing import Any

from qgis.core import QgsProject


def annotation_layer() -> Any:
    layer = QgsProject.instance().mainAnnotationLayer()
    if layer is None:
        raise ValueError("This QGIS build has no main annotation layer.")
    return layer


def list_items() -> list[dict[str, Any]]:
    layer = annotation_layer()
    described = []
    for item_id, item in (layer.items() or {}).items():
        described.append({"id": str(item_id), "kind": type(item).__name__, "text": _text_of(item)})
    return described


def remove_item(item_id: str) -> None:
    layer = annotation_layer()
    items = layer.items() or {}
    if item_id not in items:
        known = ", ".join(str(key) for key in items) or "the layer holds no annotations"
        raise ValueError(f"No annotation with id '{item_id}'. Available: {known}.")
    layer.removeItem(item_id)


def _text_of(item: Any) -> str:
    try:
        return str(item.text())
    except Exception:
        return ""
