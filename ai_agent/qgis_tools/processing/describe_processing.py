from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.processing.utils import describe_parameter, find_algorithm

MAX_HELP_CHARS = 800


class DescribeProcessingTool(BaseTool):
    name = "describe_processing"
    description = (
        "Show the parameters of a processing algorithm: names, types, whether they are "
        "required, allowed values and outputs. Call it before run_processing."
    )
    skill = "processing"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["The algorithm identifier must exist in the registry"]
    examples = ["What parameters does native:buffer take?"]
    params_schema = [
        {
            "name": "algorithm_id",
            "type": "string",
            "description": "Algorithm identifier, for example native:buffer",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        algorithm_id = (params.get("algorithm_id") or "").strip()
        if not algorithm_id:
            return tr("Reading the algorithm parameters.")
        return tr("Reading the parameters of {0}.").format(algorithm_id)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        algorithm = find_algorithm(params.get("algorithm_id") or "")
        return {
            "id": algorithm.id(),
            "name": algorithm.displayName(),
            "group": algorithm.group(),
            "help": (algorithm.shortHelpString() or "").strip()[:MAX_HELP_CHARS],
            "parameters": [describe_parameter(parameter) for parameter in algorithm.parameterDefinitions()],
            "outputs": [
                {"name": output.name(), "description": output.description()} for output in algorithm.outputDefinitions()
            ],
        }
