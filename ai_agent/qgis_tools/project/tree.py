from contextlib import suppress
from typing import Any

from qgis.core import QgsLayerTree, QgsProject

from ai_agent.qgis_tools.common.layers import find_layer_by_name

ROOT_GROUP = "root"


def project() -> QgsProject:
    return QgsProject.instance()


def layer_tree() -> Any:
    return project().layerTreeRoot()


def tree_node(layer: Any) -> Any:
    node = layer_tree().findLayer(layer.id())
    if node is None:
        raise ValueError(f"Layer '{layer.name()}' is not in the project layer tree — it may already be removed.")
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
        return "The project has no groups — omit group and the layer will land in the root."
    return "Existing groups: " + ", ".join(f"'{name}'" for name in names) + "."


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


def follow_in_drawing_order(node: Any) -> None:
    # With a custom drawing order the panel no longer decides what draws on top: move the layer there too.
    root = layer_tree()
    if not _custom_order(root):
        return
    moved = node.layer()
    if moved is None:
        return
    order = [layer for layer in root.customLayerOrder() if layer is not None and layer.id() != moved.id()]
    slot = _slot(order, *_neighbours(node))
    if slot is not None:
        order.insert(slot, moved)
        root.setCustomLayerOrder(order)


def drawn_like_panel(node: Any) -> bool:
    root = layer_tree()
    if not _custom_order(root):
        return True
    drawn = [layer.id() for layer in root.layerOrder() if layer is not None]
    moved = node.layerId()
    if moved not in drawn:
        return False
    rest = [identifier for identifier in drawn if identifier != moved]
    others = [project().mapLayer(identifier) for identifier in rest]
    return _slot(others, *_neighbours(node)) in (None, drawn.index(moved))


def _custom_order(root: Any) -> bool:
    try:
        return root.hasCustomLayerOrder() is True
    except Exception:
        return False


def _neighbours(node: Any) -> tuple[set[str], set[str]]:
    siblings = list(parent_of(node).children())
    index = siblings.index(node)
    above = {identifier for child in siblings[:index] for identifier in _layer_ids(child)}
    below = {identifier for child in siblings[index + 1 :] for identifier in _layer_ids(child)}
    return above, below


def _slot(order: list[Any], above: set[str], below: set[str]) -> int | None:
    # Over everything below it in the panel; at the very bottom, under everything above it.
    under = [index for index, layer in enumerate(order) if layer is not None and layer.id() in below]
    if under:
        return min(under)
    over = [index for index, layer in enumerate(order) if layer is not None and layer.id() in above]
    return max(over) + 1 if over else None


def _layer_ids(node: Any) -> list[str]:
    if QgsLayerTree.isLayer(node):
        return [node.layerId()]
    return [child.layerId() for child in node.findLayers()]


def _collect_groups(node: Any, names: list[str]) -> None:
    try:
        children = node.children()
    except Exception:
        return
    for child in children:
        if hasattr(child, "addGroup"):
            with suppress(Exception):
                names.append(child.name())
                _collect_groups(child, names)
