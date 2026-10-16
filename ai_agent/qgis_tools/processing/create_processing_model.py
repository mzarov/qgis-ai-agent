import os
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.processing.model_builder import (
    build_model,
    check_target,
    checked_against_registry,
    loaded_from,
    model_id,
    model_path,
    refresh_models,
    validation_issues,
)
from ai_agent.qgis_tools.processing.model_spec import INPUT_TYPES, ModelSpec, parse_model

LOG_TAG = "AI Agent"
MAX_ISSUES = 5
MAX_DETAIL_STEPS = 12
STRING = {"type": "string"}


class CreateProcessingModelTool(BaseTool):
    name = "create_processing_model"
    description = (
        "Save a chain of Processing steps as a reusable model (.model3) in the user's Models folder: it appears "
        "in the Processing Toolbox and runs on other data. A step parameter is a fixed value, "
        '{"input": "<input name>"} or {"step": "<earlier step id>", "output": "OUTPUT"}. '
        "Returns the model's algorithm id for run_processing."
    )
    skill = "processing"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = True
    network_access = False
    constraints = [
        "Algorithm ids and parameter names must exist, as describe_processing lists them",
        "A step can use only model inputs and the outputs of earlier steps",
        "Layers of this project are model inputs, never fixed values; every input must be used",
        "Leave destination parameters out of steps: outputs names the results the model returns",
        "An existing model file is never replaced unless overwrite=true",
    ]
    examples = ["Build a model from the steps I just ran", "Save this reproject-and-buffer chain as a model"]
    params_schema = [
        {
            "name": "name",
            "type": "string",
            "description": "Model name; also its file name and its id model:<name>",
            "required": True,
        },
        {"name": "group", "type": "string", "description": "Toolbox group under Models", "required": False},
        {
            "name": "description",
            "type": "string",
            "description": "One or two sentences on what the model does, shown in its dialog",
            "required": False,
        },
        {
            "name": "inputs",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": STRING,
                    "type": {"type": "string", "enum": list(INPUT_TYPES)},
                    "description": STRING,
                    "default": STRING,
                    "optional": {"type": "boolean"},
                    "parent": STRING,
                },
            },
            "description": (
                "What the user picks when running the model. name: letters, digits, underscores. parent: for a "
                "field, the vector input whose fields it lists; for a distance, the crs or layer input giving "
                "its units (leave it out when the model reprojects first)"
            ),
        },
        {
            "name": "steps",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": STRING,
                    "algorithm_id": STRING,
                    "parameters": {"type": "object"},
                    "description": STRING,
                },
            },
            "description": "The algorithms in the order they run, each with a short unique id",
        },
        {
            "name": "outputs",
            "type": "array",
            "items": {"type": "object", "properties": {"name": STRING, "step": STRING, "output": STRING}},
            "description": "Step results the model returns: a name, the step id and its output (default OUTPUT)",
        },
        {
            "name": "overwrite",
            "type": "boolean",
            "description": "Replace an existing model file. Requires an additional destructive confirmation.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        spec, _model = _checked_model(params)
        path = model_path(spec)
        check_target(model_id(spec), path, bool(params.get("overwrite")))
        return {**params, "name": spec.name, "_path": path}

    def safety_for(self, params: dict[str, Any]) -> str:
        return SAFETY_DESTRUCTIVE if params.get("overwrite") else SAFETY_WRITE

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = str(params.get("name") or "").strip()
        steps = params.get("steps")
        count = tr_n("%n step(s)", len(steps) if isinstance(steps, list) else 0)
        if not name:
            return tr("Saving the steps as a Processing model.")
        if params.get("overwrite"):
            return tr("Replace Processing model '{0}' ({1}).").format(name, count)
        return tr("Save Processing model '{0}' ({1}).").format(name, count)

    def detail_call(self, params: dict[str, Any]) -> str:
        lines = [tr("Model: {0}").format(str(params.get("name") or "").strip() or tr("unnamed"))]
        if params.get("_path"):
            lines.append(tr("File: {0}").format(params["_path"]))
        inputs = [item for item in params.get("inputs") or [] if isinstance(item, dict)]
        if inputs:
            shown = ", ".join(f"{item.get('name')} ({item.get('type')})" for item in inputs)
            lines.append(tr("Inputs: {0}").format(shown))
        steps = [item for item in params.get("steps") or [] if isinstance(item, dict)]
        lines.append(tr("Steps:"))
        lines.extend(
            f"  {index}. {item.get('id')} — {item.get('algorithm_id')}"
            for index, item in enumerate(steps[:MAX_DETAIL_STEPS], start=1)
        )
        if len(steps) > MAX_DETAIL_STEPS:
            lines.append("  …")
        return "\n".join(lines)

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        algorithm_id = str(payload.get("algorithm_id") or "")
        return tr("In the Toolbox as {0}").format(algorithm_id) if algorithm_id else ""

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        spec, model = _checked_model(params)
        algorithm_id, path = model_id(spec), model_path(spec)
        check_target(algorithm_id, path, bool(params.get("overwrite")))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not model.toFile(path):
            raise RuntimeError(f"QGIS could not write the model to '{path}'. Check that the folder is writable.")
        QgsMessageLog.logMessage(f"Saved Processing model {algorithm_id} to {path}", LOG_TAG, Qgis.MessageLevel.Info)
        refresh_models()
        if not loaded_from(algorithm_id, path):
            raise RuntimeError(
                f"The model was saved to '{path}', but the Processing Toolbox did not load it as {algorithm_id}. "
                "Tell the user where the file is: Processing → Models → Add Model to Toolbox opens it."
            )
        return {
            "algorithm_id": algorithm_id,
            "path": path,
            "inputs": [model_input.name for model_input in spec.inputs],
            "output_parameters": [definition.name() for definition in model.destinationParameterDefinitions()],
            "steps": [step.id for step in spec.steps],
            "note": "Offer to run it once with run_processing on the user's data.",
        }

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        path = str(payload.get("path") or "")
        algorithm_id = str(payload.get("algorithm_id") or "")
        return bool(path) and os.path.isfile(path) and loaded_from(algorithm_id, path)


def _checked_model(params: dict[str, Any]) -> tuple[ModelSpec, Any]:
    spec = checked_against_registry(parse_model(params))
    model = build_model(spec)
    issues = validation_issues(model)
    if issues:
        shown = "; ".join(issues[:MAX_ISSUES])
        raise ValueError(
            f"QGIS finds the model incomplete: {shown}. Give each step its required parameters "
            "(describe_processing lists them) and call again."
        )
    return spec, model
