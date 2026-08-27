from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.properties import properties_of, shown
from qgis_ai_agent.qgis_tools.project.catalogues import LAYER_PROPERTIES
from qgis_ai_agent.qgis_tools.project.tree import (
    ensure_group,
    find_layer,
    group_title,
    layer_names,
    parent_of,
    tree_node,
)


class ConfigureLayerTool(BaseTool):
    name = "configure_layer"
    description = (
        "Change a layer in the project: name, visibility, group in the layer tree, position "
        "inside the group. Leaves the data and the styling alone."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = [
        "A layer with this name must exist in the project",
        "All properties go in one call, not several",
    ]
    examples = [
        "Hide the roads layer",
        "Rename the layer to 'City roads'",
        "Move the rivers to the top",
    ]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {
            "name": "properties",
            "type": "object",
            "description": (
                "What to change, as key-value pairs: "
                '{"name": "City roads", "visible": false, "group": "Transport", '
                '"position": 0}. Pass only what actually changes.'
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        properties = LAYER_PROPERTIES.coerce_all(properties_of(params, LAYER_PROPERTIES.subject))
        if not properties:
            raise ValueError("No property was given. Available: " + ", ".join(LAYER_PROPERTIES.names()) + ".")
        _check_name(properties, layer.name())
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["properties"] = properties
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        try:
            properties = properties_of(params, LAYER_PROPERTIES.subject)
        except ValueError:
            return tr("Changing layer '{0}'.").format(layer_name)
        return tr("Changing layer '{0}': {1}.").format(layer_name, shown(properties, LAYER_PROPERTIES))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer(params.get("layer_name") or "")
        properties = LAYER_PROPERTIES.coerce_all(properties_of(params, LAYER_PROPERTIES.subject))
        node = tree_node(layer)
        if "visible" in properties:
            node.setItemVisibilityChecked(bool(properties["visible"]))
        if "name" in properties:
            layer.setName(properties["name"])
        if "group" in properties or "position" in properties:
            node = _move(layer, node, properties)
        return {
            "layer": layer.name(),
            "visible": _visible(node),
            "group": group_title(node),
            "applied": sorted(properties),
        }


def _move(layer: Any, node: Any, properties: dict[str, Any]) -> Any:
    target = ensure_group(properties["group"]) if "group" in properties else parent_of(node)
    clone = node.clone()
    parent_of(node).removeChildNode(node)
    index = int(properties.get("position", 0)) if "position" in properties else 0
    target.insertChildNode(min(index, len(target.children())), clone)
    return clone


def _visible(node: Any) -> bool:
    try:
        return bool(node.itemVisibilityChecked())
    except Exception:
        return True


def _check_name(properties: dict[str, Any], current: str) -> None:
    wanted = str(properties.get("name") or "").strip()
    if not wanted:
        return
    if wanted != current and wanted in layer_names():
        raise ValueError(f"A layer named '{wanted}' is already in the project — pick another name.")
    properties["name"] = wanted
