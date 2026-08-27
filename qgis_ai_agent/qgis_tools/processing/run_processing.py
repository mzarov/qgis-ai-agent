from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.processing.units import check_distance_units
from qgis_ai_agent.qgis_tools.processing.utils import (
    apply_output_name,
    coerce_parameters,
    find_algorithm,
    normalize_output,
)

PROCESSING_MISSING_MSG = "The Processing plugin is not available. Enable it in Plugins → Manage and Install Plugins."
MAX_SUMMARY_PARAMS = 3


class RunProcessingTool(BaseTool):
    name = "run_processing"
    description = (
        "Run a QGIS processing algorithm with the given parameters. "
        "Check the signature with describe_processing first. "
        "By default the result is added to the project."
    )
    skill = "processing"
    safety = SAFETY_WRITE
    constraints = [
        "The algorithm identifier must exist in the registry",
        "Parameter names must match describe_processing exactly",
        "Distances in metres require a layer in a metric CRS",
    ]
    examples = ["Build a 500 metre buffer around the roads", "Reproject the layer to UTM"]
    params_schema = [
        {
            "name": "algorithm_id",
            "type": "string",
            "description": "Algorithm identifier, for example native:buffer",
            "required": True,
        },
        {
            "name": "parameters",
            "type": "object",
            "description": (
                "Object holding the algorithm parameters. Layers are given by name, "
                "the output is usually 'TEMPORARY_OUTPUT'."
            ),
            "required": True,
        },
        {
            "name": "output_name",
            "type": "string",
            "description": ("Name for the resulting layer. Set it when a later step will refer to this result."),
            "required": False,
        },
        {
            "name": "load_output",
            "type": "boolean",
            "description": "Add the result to the project (true by default)",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        _, prepared = self._prepare(params)
        return {**params, "parameters": prepared}

    def summarize_call(self, params: dict[str, Any]) -> str:
        algorithm_id = (params.get("algorithm_id") or "").strip()
        arguments = params.get("parameters") or {}
        shown = ", ".join(f"{key}={value}" for key, value in list(arguments.items())[:MAX_SUMMARY_PARAMS])
        tail = "…" if len(arguments) > MAX_SUMMARY_PARAMS else ""
        output_name = (params.get("output_name") or "").strip()
        result_part = f" → '{output_name}'" if output_name else ""
        return tr("Run {0} ({1}{2}){3}.").format(algorithm_id, shown, tail, result_part)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        algorithm, prepared = self._prepare(params)
        load_output = self._resolve_load_output(params)
        runner = self._get_runner(load_output)

        result = runner(algorithm.id(), prepared)
        layer_name = apply_output_name(result, params.get("output_name") or "") if load_output else ""
        return {
            "algorithm_id": algorithm.id(),
            "loaded_to_project": load_output,
            "result_layer_name": layer_name,
            "parameters_used": prepared,
            "outputs": normalize_output(result),
        }

    @staticmethod
    def _prepare(params: dict[str, Any]) -> dict[str, Any]:
        algorithm = find_algorithm(params.get("algorithm_id") or "")
        arguments = params.get("parameters")
        if not isinstance(arguments, dict):
            raise ValueError("The parameters argument must be an object.")
        prepared = coerce_parameters(algorithm, arguments)
        check_distance_units(algorithm, prepared)
        return algorithm, prepared

    @staticmethod
    def _resolve_load_output(params: dict[str, Any]) -> bool:
        load_output = params.get("load_output")
        return True if load_output is None else bool(load_output)

    @staticmethod
    def _get_runner(load_output: bool) -> Any:
        try:
            import processing
        except ImportError:
            raise RuntimeError(PROCESSING_MISSING_MSG) from None
        return processing.runAndLoadResults if load_output else processing.run
