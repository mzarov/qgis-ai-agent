from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.processing.utils import describe_parameter, find_algorithm


class DescribeProcessingTool(BaseTool):
    """Описание сигнатуры алгоритма обработки перед его запуском."""
    name = "describe_processing"
    description = (
        "Показать параметры алгоритма обработки: имена, типы, обязательность, "
        "допустимые значения и выходы. Вызывать перед run_processing."
    )
    skill = "processing"
    safety = SAFETY_READ
    capabilities = ["processing:describe"]
    examples = ["Какие параметры у native:buffer?"]
    constraints = ["Идентификатор алгоритма должен существовать в реестре"]
    params_schema = [
        {
            "name": "algorithm_id",
            "type": "string",
            "description": "Идентификатор алгоритма, например native:buffer",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага чтения сигнатуры алгоритма."""
        algorithm_id = (params.get("algorithm_id") or "").strip()
        return f"Смотрю параметры {algorithm_id}." if algorithm_id else "Смотрю параметры алгоритма."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        algorithm = find_algorithm(params.get("algorithm_id") or "")
        return {
            "id": algorithm.id(),
            "name": algorithm.displayName(),
            "group": algorithm.group(),
            "help": (algorithm.shortHelpString() or "").strip()[:800],
            "parameters": [
                describe_parameter(parameter)
                for parameter in algorithm.parameterDefinitions()
            ],
            "outputs": [
                {"name": output.name(), "description": output.description()}
                for output in algorithm.outputDefinitions()
            ],
        }
