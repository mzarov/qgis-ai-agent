from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.expressions import compile_expression
from ai_agent.qgis_tools.fields.schema import (
    FIELD_TYPES,
    build_field,
    checked_new_name,
    commit,
    field_names,
    require_field_index,
    require_vector,
    start_editing,
)

VIRTUAL_NOTE = (
    "A virtual field is computed on the fly and stored in the project, not in "
    "the data source. It disappears if the layer is reloaded from scratch."
)


class AddFieldTool(BaseTool):
    name = "add_field"
    description = (
        "Add an attribute field to a vector layer. A plain field is written "
        "into the data source and starts empty; a virtual field is an "
        "expression computed on the fly and stored in the project only."
    )
    skill = "fields"
    safety = SAFETY_WRITE
    constraints = [
        "The field name must be new in this layer",
        "A virtual field requires a valid QGIS expression",
    ]
    examples = ["Add a text field called status", "Add a virtual field with the area in hectares"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {"name": "name", "type": "string", "description": "New field name", "required": True},
        {
            "name": "type",
            "type": "string",
            "enum": sorted(FIELD_TYPES),
            "description": "Field type; ignored for a virtual field, whose type follows the expression",
            "required": False,
        },
        {
            "name": "expression",
            "type": "string",
            "description": 'QGIS expression making this a virtual field, e.g. "$area / 10000"',
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        name = checked_new_name(layer, params.get("name"))
        expression = str(params.get("expression") or "").strip()
        if expression:
            compile_expression(expression, name, layer)
        else:
            build_field(name, params.get("type") or "text")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        prepared["name"] = name
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("name") or "").strip()
        layer_name = (params.get("layer_name") or "").strip()
        if str(params.get("expression") or "").strip():
            return tr("Adding virtual field '{0}' to '{1}'.").format(name, layer_name)
        return tr("Adding field '{0}' to '{1}'.").format(name, layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        name = checked_new_name(layer, params.get("name"))
        expression = str(params.get("expression") or "").strip()
        if expression:
            compile_expression(expression, name, layer)
            layer.addExpressionField(expression, build_field(name, params.get("type") or "double"))
            return {"layer": layer.name(), "field": name, "virtual": True, "note": VIRTUAL_NOTE}
        start_editing(layer)
        layer.addAttribute(build_field(name, params.get("type") or "text"))
        commit(layer)
        return {"layer": layer.name(), "field": name, "virtual": False}


class RenameFieldTool(BaseTool):
    name = "rename_field"
    description = "Rename an attribute field of a vector layer, keeping its values."
    skill = "fields"
    safety = SAFETY_WRITE
    constraints = ["The old field must exist and the new name must be free"]
    examples = ["Rename nm to name"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {"name": "name", "type": "string", "description": "Current field name", "required": True},
        {"name": "new_name", "type": "string", "description": "New field name", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        require_field_index(layer, params.get("name") or "")
        checked_new_name(layer, params.get("new_name"))
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Renaming field '{0}' to '{1}'.").format(
            str(params.get("name") or ""), str(params.get("new_name") or "")
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        index = require_field_index(layer, params.get("name") or "")
        new_name = checked_new_name(layer, params.get("new_name"))
        start_editing(layer)
        layer.renameAttribute(index, new_name)
        commit(layer)
        return {"layer": layer.name(), "renamed": params.get("name"), "to": new_name}


class DeleteFieldTool(BaseTool):
    name = "delete_field"
    description = (
        "Remove an attribute field from a vector layer together with all its "
        "values. This changes the data source and cannot be undone."
    )
    skill = "fields"
    safety = SAFETY_DESTRUCTIVE
    constraints = ["The field must exist", "The layer must keep at least one field"]
    examples = ["Delete the empty notes column"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Layer name exactly as in the project",
            "required": True,
        },
        {"name": "name", "type": "string", "description": "Field to remove", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        require_field_index(layer, params.get("name") or "")
        if len(field_names(layer)) <= 1:
            raise ValueError("This is the layer's only field — removing it would leave no attributes at all.")
        prepared = dict(params)
        prepared["layer_name"] = layer.name()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Deleting field '{0}' from '{1}'.").format(
            str(params.get("name") or ""), (params.get("layer_name") or "").strip()
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = require_vector(params.get("layer_name") or "")
        index = require_field_index(layer, params.get("name") or "")
        start_editing(layer)
        layer.deleteAttribute(index)
        commit(layer)
        return {"layer": layer.name(), "deleted": params.get("name")}
