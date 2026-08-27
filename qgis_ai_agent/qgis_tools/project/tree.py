from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name

ROOT_GROUP = "корень"


def project() -> QgsProject:
    return QgsProject.instance()


def layer_tree() -> Any:
    return project().layerTreeRoot()


def tree_node(layer: Any) -> Any:
    node = layer_tree().findLayer(layer.id())
    if node is None:
        raise ValueError(
            f"Слоя «{layer.name()}» нет в дереве слоёв проекта — возможно, он уже удалён."
        )
    return node


def ensure_group(name: str) -> Any:
    wanted = (name or "").strip()
    if not wanted:
        return layer_tree()
    found = layer_tree().findGroup(wanted)
    return found if found is not None else layer_tree().addGroup(wanted)


def group_names() -> list[str]:
    names: list[str] = []
    _collect_groups(layer_tree(), names)
    return names


def describe_groups() -> str:
    names = group_names()
    if not names:
        return "Групп в проекте нет — не указывайте group, слой ляжет в корень."
    return "Существующие группы: " + ", ".join(f"«{name}»" for name in names) + "."


def layer_names() -> list[str]:
    try:
        return [layer.name() for layer in project().mapLayers().values()]
    except Exception:
        return []


def find_layer(name: str) -> Any:
    return find_layer_by_name(name)


def parent_of(node: Any) -> Any:
    parent = node.parent()
    return parent if parent is not None else layer_tree()


def group_title(node: Any) -> str:
    parent = parent_of(node)
    if parent is layer_tree():
        return ROOT_GROUP
    try:
        return parent.name() or ROOT_GROUP
    except Exception:
        return ROOT_GROUP


def _collect_groups(node: Any, names: list[str]) -> None:
    try:
        children = node.children()
    except Exception:
        return
    for child in children:
        if hasattr(child, "addGroup"):
            try:
                names.append(child.name())
            except Exception:
                continue
            _collect_groups(child, names)
