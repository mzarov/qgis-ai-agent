from typing import Any

from qgis.core import QgsProject, QgsVectorLayer

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common import params
from ai_agent.qgis_tools.tables.join_plan import target_layer
from ai_agent.qgis_tools.tables.joins import describe_join


class ListJoinsTool(BaseTool):
    name = "list_joins"
    description = (
        "List the table joins of a layer, or of every layer: tables, key fields, attached field names "
        "and how many distinct layer keys found a table row."
    )
    skill = "tables"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = ["Key matches are counted for local sources only"]
    examples = ["Did every district get its population?"]
    params_schema = [params.layer_name("Layer; all layers when omitted", required=False), params.layer_id()]

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("layer_name") or "").strip()
        if name:
            return tr("Reading the joins of '{0}'.").format(name)
        return tr("Reading the table joins.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("layer_name") or params.get("layer_id"):
            layers = [target_layer(params)]
        else:
            layers = [
                layer
                for layer in QgsProject.instance().mapLayers().values()
                if isinstance(layer, QgsVectorLayer) and layer.vectorJoins()
            ]
        listed = [
            {"layer": layer.name(), "joins": [describe_join(layer, join) for join in layer.vectorJoins()]}
            for layer in layers
        ]
        return {"layers": listed} if listed else {"layers": [], "note": "No layer in the project has a join."}
