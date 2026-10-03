from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import bind_layer_reference
from ai_agent.qgis_tools.tables.join_plan import target_layer
from ai_agent.qgis_tools.tables.joins import find_join, joined_field_names


class RemoveJoinTool(BaseTool):
    name = "remove_join"
    description = (
        "Remove a table join from a layer. The attached fields disappear; the table layer and the "
        "layer's own data stay."
    )
    skill = "tables"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["The layer must have a join with that table"]
    examples = ["Detach the population table from districts"]
    params_schema = [
        {"name": "layer_name", "type": "string", "description": "Layer that has the join", "required": True},
        {
            "name": "layer_id",
            "type": "string",
            "description": "Stable layer id from list_layers; required when names are duplicated",
            "required": False,
        },
        {"name": "table", "type": "string", "description": "Joined table name or id", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = target_layer(params)
        find_join(layer, params.get("table") or "")
        return bind_layer_reference(params, layer)

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Removing the join of {0} from '{1}'.").format(
            str(params.get("table") or "").strip(), str(params.get("layer_name") or "").strip()
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = target_layer(params)
        join = find_join(layer, params.get("table") or "")
        table = join.joinLayer()
        removed = joined_field_names(join, table) if table is not None else []
        if not layer.removeJoin(join.joinLayerId()):
            raise ValueError(f"QGIS refused to remove the join of '{params.get('table')}'.")
        return {"layer": layer.name(), "table": params.get("table"), "removed_fields": removed}
