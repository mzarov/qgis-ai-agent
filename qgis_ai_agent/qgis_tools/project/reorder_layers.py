from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.project.tree import find_layer, layer_tree, parent_of, tree_node

SHOWN_NAMES = 4


class ReorderLayersTool(BaseTool):
    name = "reorder_layers"
    description = (
        "Arrange the layer panel in one call: list the layer names top to bottom "
        "and they take the top of the panel in exactly that order. The first name "
        "draws over everything, the last one sits just above whatever was not "
        "listed. A layer inside a group is pulled out to the root. Prefer this "
        "over juggling position numbers layer by layer."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "Every listed layer must exist",
        "Top to bottom: the usual order is points, lines, polygons, basemap last",
    ]
    examples = [
        "Put the cafes on top, then roads, then parks, basemap at the bottom",
        "Fix the layer order",
    ]
    params_schema = [
        {
            "name": "layer_names",
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Layer names in the final top-to-bottom order. Anything not "
                "listed keeps its place below the listed ones."
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        names = _checked_names(params.get("layer_names"))
        prepared = dict(params)
        prepared["layer_names"] = [find_layer(name).name() for name in names]
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        names = [str(name) for name in params.get("layer_names") or [] if str(name).strip()]
        if not names:
            return tr("Arranging the layer order.")
        shown = " → ".join(names[:SHOWN_NAMES])
        if len(names) > SHOWN_NAMES:
            shown += " → …"
        return tr("Arranging the layers, top to bottom: {0}.").format(shown)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        names = _checked_names(params.get("layer_names"))
        root = layer_tree()
        for index, name in enumerate(names):
            node = tree_node(find_layer(name))
            clone = node.clone()
            root.insertChildNode(min(index, len(root.children())), clone)
            parent_of(node).removeChildNode(node)
        return {"order": names, "note": "Listed layers now hold the top of the panel in this order."}


def _checked_names(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("layer_names is a non-empty list of layer names, top to bottom.")
    names = [str(name).strip() for name in raw if str(name).strip()]
    if not names:
        raise ValueError("layer_names holds no usable names.")
    lowered = [name.lower() for name in names]
    if len(set(lowered)) != len(lowered):
        raise ValueError("A layer is listed twice — each name goes in once.")
    return names
