"""A checked ModelSpec as a QgsProcessingModelAlgorithm, and the folder the Models provider reads.

`checked_against_registry` resolves what only QGIS knows — algorithm ids,
parameter and output names, enum labels — so every mistake surfaces while the
call is prepared. `build_model` assembles the model the way the Model
Designer stores it; the files it writes open there like hand-made ones.
"""

import os
import re
from dataclasses import replace
from typing import Any

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessingModelAlgorithm,
    QgsProcessingModelChildAlgorithm,
    QgsProcessingModelChildParameterSource,
    QgsProcessingModelOutput,
    QgsProcessingModelParameter,
    QgsProcessingParameterCrs,
    QgsProcessingParameterDistance,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)
from qgis.PyQt.QtCore import QPointF

from ai_agent.qgis_tools.common.paths import same_path
from ai_agent.qgis_tools.processing.model_spec import (
    InputSource,
    ModelInput,
    ModelSpec,
    ModelStep,
    Source,
    StaticSource,
    StepSource,
)
from ai_agent.qgis_tools.processing.utils import (
    LAYER_PARAMETER_TYPES,
    TEMPORARY_OUTPUT,
    coerce_enum,
    destination_parameter_names,
    find_algorithm,
    get_registry,
    resolve_layer,
)

MODEL_PROVIDER_ID = "model"
MODEL_ID_PREFIX = MODEL_PROVIDER_ID + ":"
MODEL_SUFFIX = ".model3"
HELP_DESCRIPTION_KEY = "ALG_DESC"
SCRATCH_PREFIXES = ("memory:", "memory://")
HTML_TAG = re.compile(r"<[^>]+>")
MAX_LISTED_NAMES = 12
# Designer coordinates: inputs in a row on top, steps in a column below, each output beside its step.
INPUT_ROW = (120.0, 60.0, 220.0)
STEP_COLUMN = (320.0, 200.0, 160.0)
OUTPUT_OFFSET = (230.0, 60.0)


def checked_against_registry(spec: ModelSpec) -> ModelSpec:
    """The spec with canonical algorithm ids and enum indexes; ValueError for anything QGIS would refuse."""
    algorithms: dict[str, Any] = {}
    steps: list[ModelStep] = []
    for step in spec.steps:
        try:
            algorithm = find_algorithm(step.algorithm_id)
        except ValueError as failure:
            raise ValueError(f"Step '{step.id}': {failure}") from None
        algorithms[step.id] = algorithm
        steps.append(replace(step, algorithm_id=algorithm.id(), sources=_checked_sources(step, algorithm, algorithms)))
    for output in spec.outputs:
        destinations = destination_parameter_names(algorithms[output.step])
        if output.output not in destinations:
            raise ValueError(
                f"Output '{output.name}' takes {output.output} of step '{output.step}', which is not one of its "
                f"outputs. Use one of: {_listed(destinations)}."
            )
    return replace(spec, steps=steps)


def build_model(spec: ModelSpec) -> Any:
    model = QgsProcessingModelAlgorithm(spec.name, spec.group)
    if spec.description:
        model.setHelpContent({HELP_DESCRIPTION_KEY: spec.description})
    left, top, spacing = INPUT_ROW
    for index, model_input in enumerate(spec.inputs):
        component = QgsProcessingModelParameter(model_input.name)
        component.setPosition(QPointF(left + index * spacing, top))
        model.addModelParameter(parameter_definition(model_input), component)
    for index, step in enumerate(spec.steps):
        model.addChildAlgorithm(_child(spec, step, index))
    model.updateDestinationParameters()
    return model


def parameter_definition(model_input: ModelInput) -> Any:
    name, text = model_input.name, model_input.description
    default, optional, kind = model_input.default, model_input.optional, model_input.kind
    if kind == "vector":
        return QgsProcessingParameterVectorLayer(name, text, types=[], defaultValue=default, optional=optional)
    if kind == "raster":
        return QgsProcessingParameterRasterLayer(name, text, defaultValue=default, optional=optional)
    if kind == "number":
        number = Qgis.ProcessingNumberParameterType.Double
        return QgsProcessingParameterNumber(name, text, type=number, defaultValue=default, optional=optional)
    if kind == "distance":
        parent = model_input.parent
        return QgsProcessingParameterDistance(
            name, text, defaultValue=default, parentParameterName=parent, optional=optional
        )
    if kind == "field":
        return QgsProcessingParameterField(
            name,
            text,
            defaultValue=default,
            parentLayerParameterName=model_input.parent,
            type=Qgis.ProcessingFieldParameterDataType.Any,
            allowMultiple=False,
            optional=optional,
        )
    if kind == "crs":
        return QgsProcessingParameterCrs(name, text, defaultValue=default, optional=optional)
    return QgsProcessingParameterString(name, text, defaultValue=default, multiLine=False, optional=optional)


def validation_issues(model: Any) -> list[str]:
    """What QGIS's own model check finds, as plain text (it marks names up in HTML for its dialogs)."""
    _valid, issues = model.validate()
    return [HTML_TAG.sub("", str(issue)).strip() for issue in issues or []]


def model_id(spec: ModelSpec) -> str:
    return MODEL_ID_PREFIX + spec.name


def models_folder() -> str:
    """The first folder of the Models provider: where the Model Designer saves and what the Toolbox lists."""
    try:
        # The Processing plugin can be switched off; its absence must not break importing the tool.
        from processing.modeler.ModelerUtils import ModelerUtils

        folders = [str(folder) for folder in ModelerUtils.modelsFolders() if folder]
    except Exception:
        folders = []
    if folders:
        return folders[0]
    return os.path.join(str(QgsApplication.qgisSettingsDirPath()), "processing", "models")


def model_path(spec: ModelSpec) -> str:
    return os.path.join(models_folder(), spec.name + MODEL_SUFFIX)


def check_target(algorithm_id: str, path: str, overwrite: bool) -> None:
    """Refuse to replace a model file without overwrite, and to shadow a model loaded from elsewhere."""
    loaded = registered_model(algorithm_id)
    source = _source_path(loaded)
    if loaded is not None and not (source and same_path(source, path)):
        where = f" from '{source}'" if source else ""
        raise ValueError(f"A model {algorithm_id} is already loaded{where}. Pick another name.")
    if os.path.lexists(path) and not overwrite:
        raise ValueError(
            f"The model file '{path}' already exists. Pick another name, or pass overwrite=true only after "
            "the user agreed to replace it."
        )


def refresh_models() -> None:
    provider = get_registry().providerById(MODEL_PROVIDER_ID)
    if provider is None:
        raise RuntimeError("The Models provider of Processing is not loaded. Check that Processing is enabled.")
    provider.refreshAlgorithms()


def registered_model(algorithm_id: str) -> Any:
    return get_registry().algorithmById(algorithm_id) if algorithm_id else None


def loaded_from(algorithm_id: str, path: str) -> bool:
    source = _source_path(registered_model(algorithm_id))
    return bool(source) and same_path(source, path)


def _source_path(algorithm: Any) -> str:
    try:
        return str(algorithm.sourceFilePath() or "") if algorithm is not None else ""
    except AttributeError:
        return ""


def _checked_sources(step: ModelStep, algorithm: Any, algorithms: dict[str, Any]) -> dict[str, Source]:
    definitions = {definition.name(): definition for definition in algorithm.parameterDefinitions()}
    destinations = set(destination_parameter_names(algorithm))
    sources: dict[str, Source] = {}
    for name, source in step.sources.items():
        definition = definitions.get(name)
        if definition is None:
            accepted = [key for key in definitions if key not in destinations]
            raise ValueError(
                f"Step '{step.id}' ({algorithm.id()}) has no parameter {name}. Its parameters: {_listed(accepted)}. "
                "Check the exact names with describe_processing."
            )
        if name in destinations:
            if isinstance(source, StaticSource) and _temporary(source.value):
                continue
            raise ValueError(
                f"Step '{step.id}' parameter {name} is where the step writes its result. Leave it out: list the "
                "result in outputs to return it, and the user picks the path when the model runs."
            )
        if isinstance(source, StepSource):
            _check_step_output(step, name, source, algorithms[source.step])
        if isinstance(source, StaticSource):
            source = StaticSource(_static_value(step, definition, source.value))
        sources[name] = source
    return sources


def _check_step_output(step: ModelStep, parameter: str, source: StepSource, upstream: Any) -> None:
    outputs = [output.name() for output in upstream.outputDefinitions()]
    if source.output not in outputs:
        raise ValueError(
            f"Step '{step.id}' parameter {parameter} takes {source.output} of step '{source.step}', which has no "
            f"such output. Its outputs: {_listed(outputs)}."
        )


def _static_value(step: ModelStep, definition: Any, value: Any) -> Any:
    kind = str(definition.type()).lower()
    if kind == "enum":
        return coerce_enum(definition, value)
    if kind in LAYER_PARAMETER_TYPES:
        for item in value if isinstance(value, list) else [value]:
            _refuse_project_layer(step, definition.name(), item)
    return value


def _refuse_project_layer(step: ModelStep, parameter: str, value: Any) -> None:
    """A model runs in other projects: a layer of this one, or a scratch layer, must become a model input."""
    if not isinstance(value, str) or not value.strip():
        return
    text = value.strip()
    layer = resolve_layer(text)
    if layer is None and not text.lower().startswith(SCRATCH_PREFIXES):
        return
    shown = f"layer '{layer.name()}' of this project" if layer is not None else "a scratch layer"
    raise ValueError(
        f"Step '{step.id}' parameter {parameter} names {shown}, which another project will not have. Declare a "
        f'model input (type vector or raster) and pass {{"input": "<its name>"}} instead.'
    )


def _child(spec: ModelSpec, step: ModelStep, index: int) -> Any:
    child = QgsProcessingModelChildAlgorithm(step.algorithm_id)
    child.setChildId(step.id)
    child.setDescription(step.description or _display_name(step.algorithm_id))
    left, top, spacing = STEP_COLUMN
    position = QPointF(left, top + index * spacing)
    child.setPosition(position)
    for name, source in step.sources.items():
        child.addParameterSources(name, [_child_source(source)])
    outputs = {}
    for output in (item for item in spec.outputs if item.step == step.id):
        component = QgsProcessingModelOutput(output.name, output.name)
        component.setChildId(step.id)
        component.setChildOutputName(output.output)
        component.setPosition(QPointF(position.x() + OUTPUT_OFFSET[0], position.y() + OUTPUT_OFFSET[1]))
        outputs[output.name] = component
    child.setModelOutputs(outputs)
    return child


def _child_source(source: Source) -> Any:
    if isinstance(source, InputSource):
        return QgsProcessingModelChildParameterSource.fromModelParameter(source.input)
    if isinstance(source, StepSource):
        return QgsProcessingModelChildParameterSource.fromChildOutput(source.step, source.output)
    return QgsProcessingModelChildParameterSource.fromStaticValue(source.value)


def _display_name(algorithm_id: str) -> str:
    algorithm = get_registry().algorithmById(algorithm_id)
    return str(algorithm.displayName()) if algorithm is not None else algorithm_id


def _temporary(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() == TEMPORARY_OUTPUT


def _listed(names: list[str]) -> str:
    shown = ", ".join(names[:MAX_LISTED_NAMES])
    return shown + (", …" if len(names) > MAX_LISTED_NAMES else "") if shown else "none"
