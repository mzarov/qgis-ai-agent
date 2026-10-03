from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.layers import bind_layer_reference, layer_identifier
from ai_agent.qgis_tools.tables.join_plan import JoinPlan, plan_join
from ai_agent.qgis_tools.tables.source import free_layer_name, open_delimited

LOG_TAG = "AI Agent"
PARTIAL_NOTE = "Some features found no table row; their joined fields are NULL. See unmatched_samples."
UNCHECKED_NOTE = "Keys were not compared (a remote or very large source); check the result with list_joins."


class JoinTableTool(BaseTool):
    name = "join_table"
    description = (
        "Attach a table's attributes to a vector layer by a shared key (a live QGIS join, kept in the "
        "project; the layer's own data is not changed). The table is a project layer or a path to a "
        "CSV/TSV/TXT file, which is then loaded as a table first."
    )
    skill = "tables"
    safety = SAFETY_WRITE
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = [
        "Both key fields must exist and share at least one value",
        "A table can be joined to a layer once",
    ]
    examples = ["Attach population.csv to districts by code"]
    params_schema = [
        {"name": "layer_name", "type": "string", "description": "Layer that receives the fields", "required": True},
        {
            "name": "layer_id",
            "type": "string",
            "description": "Stable layer id from list_layers; required when names are duplicated",
            "required": False,
        },
        {"name": "layer_field", "type": "string", "description": "Key field of the layer", "required": True},
        {"name": "table", "type": "string", "description": "Project layer name, or a file path", "required": True},
        {"name": "table_field", "type": "string", "description": "Key field of the table", "required": True},
        {
            "name": "fields",
            "type": "array",
            "items": {"type": "string"},
            "description": "Table fields to attach; all but the key when omitted",
            "required": False,
        },
        {
            "name": "prefix",
            "type": "string",
            "description": 'Prefix of the attached field names; "<table>_" when omitted, "" for none',
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        plan = plan_join(params)
        report = plan.match()
        if report is not None and report["target_keys"] and not report["matched_keys"]:
            raise ValueError(
                f"No value of '{plan.target.name()}'.{plan.layer_field} matches "
                f"'{plan.table_name}'.{plan.table_field}: layer keys {report['unmatched_samples']}, "
                f"table keys {report.get('table_samples', [])}. {report.get('hint', '')}"
            )
        prepared = bind_layer_reference(params, plan.target)
        prepared.update({"layer_field": plan.layer_field, "table_field": plan.table_field, "prefix": plan.prefix})
        if plan.subset:
            prepared["fields"] = plan.subset
        else:
            prepared.pop("fields", None)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Joining {0} to '{1}' by {2} = {3}.").format(
            str(params.get("table") or "").strip(),
            str(params.get("layer_name") or "").strip(),
            str(params.get("layer_field") or "").strip(),
            str(params.get("table_field") or "").strip(),
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        plan = plan_join(params)
        table_layer, loaded = _table_layer(plan)
        if not plan.target.addJoin(plan.join_info(table_layer)):
            if loaded:
                QgsProject.instance().removeMapLayer(layer_identifier(table_layer))
            raise ValueError(f"QGIS refused to join '{plan.table_name}' to '{plan.target.name()}'.")
        QgsMessageLog.logMessage(f"Joined {plan.table_name} to {plan.target.name()}", LOG_TAG, Qgis.MessageLevel.Info)
        result: dict[str, Any] = {
            "layer": plan.target.name(),
            "table": table_layer.name(),
            "joined_fields": plan.joined_fields,
        }
        if loaded:
            result["loaded_table"] = table_layer.name()
        report = plan.match()
        if report is None:
            result["note"] = UNCHECKED_NOTE
        else:
            result["match"] = report
            if report["unmatched_keys"]:
                result["note"] = PARTIAL_NOTE
        return result


def _table_layer(plan: JoinPlan) -> tuple[Any, bool]:
    """The join layer, loading the file into the project when it is not there yet."""
    if plan.table_layer is not None:
        return plan.table_layer, False
    if plan.table_file is None:
        raise ValueError("The join has no table.")
    layer = open_delimited(plan.table_file, free_layer_name(plan.table_file.stem))
    QgsProject.instance().addMapLayer(layer)
    plan.table_layer = layer
    return layer, True
