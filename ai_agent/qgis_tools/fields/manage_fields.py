from collections.abc import Callable
from typing import Any

from qgis.core import QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.common.expressions import compile_expression
from ai_agent.qgis_tools.common.layers import bind_layer_reference, find_layer_by_id, pinned_layer
from ai_agent.qgis_tools.fields.schema import (
    FIELD_TYPES,
    build_field,
    build_virtual_field,
    checked_new_name,
    field_names,
    infer_virtual_type,
    is_virtual_field,
    require_field_index,
    require_vector,
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
    egress = EGRESS_METADATA
    network_access = False
    constraints = [
        "The field name must be new in this layer",
        "A virtual field requires a valid QGIS expression",
    ]
    examples = ["Add a text field called status", "Add a virtual field with the area in hectares"]
    params_schema = [
        params.layer_name(),
        params.layer_id(),
        {"name": "name", "type": "string", "description": "New field name", "required": True},
        {
            "name": "type",
            "type": "string",
            "enum": sorted(FIELD_TYPES),
            "description": (
                "Field type. For a virtual field omit it: the type is inferred from the "
                "expression's values (text when the layer has no features to evaluate)"
            ),
            "required": False,
        },
        {
            "name": "expression",
            "type": "string",
            "description": 'QGIS expression making this a virtual field, e.g. "$area / 10000"',
            "required": False,
        },
    ]

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        return not bool(str(params.get("expression") or "").strip())

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        expression = str(params.get("expression") or "").strip()
        name = checked_new_name(layer, params.get("name"), stored=not expression)
        prepared = bind_layer_reference(params, layer)
        if expression:
            compile_expression(expression, name, layer)
            kind = str(params.get("type") or "").strip().lower() or infer_virtual_type(layer, expression)
            build_virtual_field(name, kind)
            prepared["type"] = kind
        else:
            build_field(name, params.get("type") or "text")
        prepared["name"] = name
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("name") or "").strip()
        layer_name = (params.get("layer_name") or "").strip()
        if str(params.get("expression") or "").strip():
            return tr("Adding virtual field '{0}' to '{1}'.").format(name, layer_name)
        return tr("Adding field '{0}' to '{1}'.").format(name, layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        expression = str(params.get("expression") or "").strip()
        name = checked_new_name(layer, params.get("name"), stored=not expression)
        if expression:
            compile_expression(expression, name, layer)
            kind = str(params.get("type") or "").strip().lower() or infer_virtual_type(layer, expression)
            index = layer.addExpressionField(expression, build_virtual_field(name, kind))
            if index < 0:
                raise ValueError(f"QGIS refused to add virtual field '{name}'.")
            return {"layer": layer.name(), "field": name, "virtual": True, "type": kind, "note": VIRTUAL_NOTE}
        field = build_field(name, params.get("type") or "text")
        before = field_names(layer)
        with edit_session(layer, "the schema change"):
            if not layer.addAttribute(field):
                raise ValueError(f"QGIS refused to add field '{name}'.")
        return {"layer": layer.name(), "field": _stored_name(layer, before, name), "virtual": False}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        if str(params.get("expression") or "").strip():
            return None
        return _has_field(params, params.get("name"))


def _stored_name(layer: QgsVectorLayer, before: list[str], wanted: str) -> str:
    # A format may store the name its own way: report what the layer has now.
    added = [name for name in field_names(layer) if name not in before]
    return wanted if wanted in added or not added else added[-1]


class RenameFieldTool(BaseTool):
    name = "rename_field"
    description = "Rename an attribute field of a vector layer, keeping its values."
    skill = "fields"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    network_access = False
    external_effect = True
    constraints = ["The old field must exist and the new name must be free"]
    examples = ["Rename nm to name"]
    params_schema = [
        params.layer_name(),
        params.layer_id(),
        {"name": "name", "type": "string", "description": "Current field name", "required": True},
        {"name": "new_name", "type": "string", "description": "New field name", "required": True},
    ]

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        return not _targets_virtual(params)

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        index = require_field_index(layer, params.get("name") or "")
        checked_new_name(layer, params.get("new_name"), stored=not is_virtual_field(layer, index))
        return bind_layer_reference(params, layer)

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Renaming field '{0}' to '{1}'.").format(
            str(params.get("name") or ""), str(params.get("new_name") or "")
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        index = require_field_index(layer, params.get("name") or "")
        virtual = is_virtual_field(layer, index)
        new_name = checked_new_name(layer, params.get("new_name"), stored=not virtual)
        refusal = f"QGIS refused to rename field '{params.get('name')}'."
        _change_schema(layer, virtual, lambda: layer.renameAttribute(index, new_name), refusal)
        stored = field_names(layer)[index : index + 1]
        landed = stored[0] if stored and stored[0] != params.get("name") else new_name
        return {"layer": layer.name(), "renamed": params.get("name"), "to": landed}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        return _has_field(params, params.get("new_name")) and not _has_field(params, params.get("name"))


class DeleteFieldTool(BaseTool):
    name = "delete_field"
    description = (
        "Remove an attribute field from a vector layer together with all its "
        "values. This changes the data source and cannot be undone."
    )
    skill = "fields"
    safety = SAFETY_DESTRUCTIVE
    egress = EGRESS_METADATA
    network_access = False
    external_effect = True
    constraints = ["The field must exist", "The layer must keep at least one field"]
    examples = ["Delete the empty notes column"]
    params_schema = [
        params.layer_name(),
        params.layer_id(),
        {"name": "name", "type": "string", "description": "Field to remove", "required": True},
    ]

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        return not _targets_virtual(params)

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        require_field_index(layer, params.get("name") or "")
        if len(field_names(layer)) <= 1:
            raise ValueError("This is the layer's only field — removing it would leave no attributes at all.")
        return bind_layer_reference(params, layer)

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Deleting field '{0}' from '{1}'.").format(
            str(params.get("name") or ""), (params.get("layer_name") or "").strip()
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = _field_target(params)
        index = require_field_index(layer, params.get("name") or "")
        if len(field_names(layer)) <= 1:
            raise ValueError("This is the layer's only field — removing it would leave no attributes at all.")
        refusal = f"QGIS refused to delete field '{params.get('name')}'."
        _change_schema(layer, is_virtual_field(layer, index), lambda: layer.deleteAttribute(index), refusal)
        return {"layer": layer.name(), "deleted": params.get("name")}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        layer = pinned_layer(params)
        return layer is not None and not _has_field(params, params.get("name"))


def _change_schema(layer: QgsVectorLayer, virtual: bool, change: Callable[[], bool], refusal: str) -> None:
    # A virtual field lives in the project: a read-only source cannot open an edit session, and needs none.
    if virtual:
        if not change():
            raise ValueError(refusal)
        return
    with edit_session(layer, "the schema change"):
        if not change():
            raise ValueError(refusal)


def _targets_virtual(params: dict[str, Any]) -> bool:
    try:
        layer = _field_target(params)
        return is_virtual_field(layer, require_field_index(layer, params.get("name") or ""))
    except Exception:
        return False


def _has_field(params: dict[str, Any], name: Any) -> bool:
    layer = pinned_layer(params)
    wanted = str(name or "").strip()
    return layer is not None and bool(wanted) and wanted in field_names(layer)


def _field_target(params: dict[str, Any]) -> QgsVectorLayer:
    layer_id = str(params.get("layer_id") or "").strip()
    if not layer_id:
        return require_vector(params.get("layer_name") or "")
    layer = find_layer_by_id(layer_id)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"Layer '{layer.name()}' is not a vector layer, it has no attribute schema.")
    return layer
