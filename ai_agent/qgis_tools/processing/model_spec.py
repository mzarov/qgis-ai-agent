import re
from dataclasses import dataclass
from typing import Any

INPUT_TYPES = ("vector", "raster", "number", "distance", "field", "string", "crs")
NUMERIC_INPUT_TYPES = ("number", "distance")
PARENT_TYPES = {"field": ("vector",), "distance": ("vector", "raster", "crs")}
INPUT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# The model name is its file name: these characters break a path on some platform.
FORBIDDEN_NAME_CHARACTERS = '/\\:*?"<>|'
MAX_NAME_CHARS = 80
MAX_INPUTS = 20
MAX_STEPS = 30
DEFAULT_OUTPUT = "OUTPUT"
INPUT_KEY = "input"
STEP_KEY = "step"
OUTPUT_KEY = "output"
REFERENCE_KEYS = frozenset({INPUT_KEY, STEP_KEY, OUTPUT_KEY})


@dataclass(frozen=True)
class ModelInput:
    name: str
    kind: str
    description: str
    default: Any = None
    optional: bool = False
    parent: str = ""


@dataclass(frozen=True)
class InputSource:
    input: str


@dataclass(frozen=True)
class StepSource:
    step: str
    output: str


@dataclass(frozen=True)
class StaticSource:
    value: Any


Source = InputSource | StepSource | StaticSource


@dataclass(frozen=True)
class ModelStep:
    id: str
    algorithm_id: str
    description: str
    sources: dict[str, Source]


@dataclass(frozen=True)
class ModelOutput:
    name: str
    step: str
    output: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    group: str
    description: str
    inputs: list[ModelInput]
    steps: list[ModelStep]
    outputs: list[ModelOutput]


def parse_model(params: dict[str, Any]) -> ModelSpec:
    name = model_name(params.get("name"))
    inputs = parse_inputs(params.get("inputs"))
    steps = parse_steps(params.get("steps"), inputs)
    outputs = parse_outputs(params.get("outputs"), steps, inputs)
    _check_every_input_used(inputs, steps)
    return ModelSpec(
        name=name,
        group=_text(params.get("group")),
        description=_text(params.get("description")),
        inputs=inputs,
        steps=steps,
        outputs=outputs,
    )


def model_name(value: Any) -> str:
    name = _text(value)
    if not name:
        raise ValueError("The model needs a name, for example 'Buffer in UTM'.")
    if len(name) > MAX_NAME_CHARS:
        raise ValueError(f"The model name is longer than {MAX_NAME_CHARS} characters. Shorten it.")
    bad = sorted({character for character in name if character in FORBIDDEN_NAME_CHARACTERS})
    if bad or name.startswith("."):
        shown = " ".join(bad) or "a leading dot"
        raise ValueError(f"The model name is also its file name and cannot hold {shown}. Pick a plainer name.")
    return name


def parse_inputs(raw: Any) -> list[ModelInput]:
    items = _objects(raw, "inputs", allow_empty=True)
    if len(items) > MAX_INPUTS:
        raise ValueError(f"A model takes at most {MAX_INPUTS} inputs.")
    drafts: list[ModelInput] = []
    for item in items:
        name = _text(item.get("name"))
        if not INPUT_NAME.match(name):
            raise ValueError(
                f"Input name '{name}' is not usable as a parameter name. Use letters, digits and underscores, "
                "for example input_layer; put the friendly text in description."
            )
        if any(existing.name.lower() == name.lower() for existing in drafts):
            raise ValueError(f"Two inputs are named '{name}'. Give each input its own name.")
        kind = _text(item.get("type")).lower()
        if kind not in INPUT_TYPES:
            raise ValueError(f"Input '{name}' has type '{kind}'. Use one of: {', '.join(INPUT_TYPES)}.")
        drafts.append(
            ModelInput(
                name=name,
                kind=kind,
                description=_text(item.get("description")) or name,
                default=_default(name, kind, item.get("default")),
                optional=bool(item.get("optional")),
                parent=_text(item.get("parent")),
            )
        )
    return [_with_parent(model_input, drafts) for model_input in drafts]


def parse_steps(raw: Any, inputs: list[ModelInput]) -> list[ModelStep]:
    items = _objects(raw, "steps")
    if len(items) > MAX_STEPS:
        raise ValueError(f"A model holds at most {MAX_STEPS} steps.")
    all_ids = [_text(item.get("id")) for item in items]
    input_names = [model_input.name for model_input in inputs]
    steps: list[ModelStep] = []
    for index, item in enumerate(items):
        step_id = all_ids[index]
        if not step_id:
            raise ValueError(f"Step {index + 1} has no id. Give every step a short id such as 'buffer'.")
        if step_id in all_ids[:index]:
            raise ValueError(f"Two steps have the id '{step_id}'. Give each step its own id.")
        algorithm_id = _text(item.get("algorithm_id"))
        if not algorithm_id:
            raise ValueError(f"Step '{step_id}' has no algorithm_id, for example native:buffer.")
        arguments = item.get("parameters")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError(f"Step '{step_id}': parameters must be an object of parameter name → value.")
        earlier = all_ids[:index]
        sources = {
            str(key): parse_source(value, step_id, str(key), input_names, earlier, all_ids)
            for key, value in arguments.items()
        }
        steps.append(ModelStep(step_id, algorithm_id, _text(item.get("description")), sources))
    return steps


def parse_source(
    value: Any, step_id: str, parameter: str, inputs: list[str], earlier: list[str], all_steps: list[str]
) -> Source:
    if not isinstance(value, dict) or not (value.keys() & {INPUT_KEY, STEP_KEY}):
        return StaticSource(value)
    where = f"Step '{step_id}' parameter {parameter}"
    unexpected = sorted(str(key) for key in value if key not in REFERENCE_KEYS)
    if unexpected or (INPUT_KEY in value and (STEP_KEY in value or OUTPUT_KEY in value)):
        raise ValueError(
            f'{where}: a reference is {{"input": "<input name>"}} or {{"step": "<step id>", "output": "OUTPUT"}}, '
            "nothing else in the same object."
        )
    if INPUT_KEY in value:
        name = _text(value[INPUT_KEY])
        if name not in inputs:
            declared = ", ".join(inputs) or "none"
            raise ValueError(
                f"{where} refers to an unknown input '{name}'. Declared inputs: {declared}. "
                "Add it to inputs or fix the name."
            )
        return InputSource(name)
    target = _text(value[STEP_KEY])
    if target == step_id:
        raise ValueError(f"{where} refers to its own step. A step can use only the outputs of earlier steps.")
    if target not in all_steps:
        known = ", ".join(earlier) or "none"
        raise ValueError(f"{where} refers to an unknown step '{target}'. Steps before it: {known}.")
    if target not in earlier:
        raise ValueError(
            f"{where} refers to step '{target}', which comes later. List the steps in the order they run: "
            "a step can use only the outputs of earlier steps."
        )
    return StepSource(target, _text(value.get(OUTPUT_KEY)) or DEFAULT_OUTPUT)


def parse_outputs(raw: Any, steps: list[ModelStep], inputs: list[ModelInput]) -> list[ModelOutput]:
    items = _objects(raw, "outputs")
    step_ids = [step.id for step in steps]
    taken = {_parameter_key(model_input.name) for model_input in inputs}
    outputs: list[ModelOutput] = []
    for item in items:
        name = _text(item.get("name"))
        if not name:
            raise ValueError("Every model output needs a name, for example 'Buffered'.")
        key = _parameter_key(name)
        if key in taken:
            raise ValueError(f"The output name '{name}' clashes with an input or another output. Rename it.")
        taken.add(key)
        step_id = _text(item.get(STEP_KEY))
        if step_id not in step_ids:
            raise ValueError(
                f"Output '{name}' names step '{step_id}', which is not a step. Steps: {', '.join(step_ids)}."
            )
        output = ModelOutput(name, step_id, _text(item.get(OUTPUT_KEY)) or DEFAULT_OUTPUT)
        twin = next((other for other in outputs if (other.step, other.output) == (output.step, output.output)), None)
        if twin is not None:
            raise ValueError(f"{output.output} of step '{step_id}' is already the output '{twin.name}'. Keep one.")
        outputs.append(output)
    return outputs


def used_inputs(steps: list[ModelStep]) -> set[str]:
    return {source.input for step in steps for source in step.sources.values() if isinstance(source, InputSource)}


def _check_every_input_used(inputs: list[ModelInput], steps: list[ModelStep]) -> None:
    used = used_inputs(steps) | {model_input.parent for model_input in inputs if model_input.parent}
    for model_input in inputs:
        if model_input.name not in used:
            raise ValueError(
                f"Input '{model_input.name}' is never used. Pass it to a step parameter as "
                f'{{"input": "{model_input.name}"}}, or remove it.'
            )


def _with_parent(model_input: ModelInput, inputs: list[ModelInput]) -> ModelInput:
    allowed = PARENT_TYPES.get(model_input.kind)
    if allowed is None:
        if model_input.parent:
            raise ValueError(f"Input '{model_input.name}' ({model_input.kind}) takes no parent; remove it.")
        return model_input
    candidates = [other for other in inputs if other.kind in allowed and other.name != model_input.name]
    if model_input.parent:
        if model_input.parent not in [other.name for other in candidates]:
            names = ", ".join(other.name for other in candidates) or "none declared"
            raise ValueError(
                f"Input '{model_input.name}' names parent '{model_input.parent}', which is not a "
                f"{' or '.join(allowed)} input. Candidates: {names}."
            )
        return model_input
    if model_input.kind == "field":
        if len(candidates) != 1:
            raise ValueError(f"Field input '{model_input.name}' needs parent: the vector input whose fields it lists.")
        return _replace_parent(model_input, candidates[0].name)
    # Never a layer's units by default: a model that reprojects first would get degrees.
    crs_inputs = [other for other in candidates if other.kind == "crs"]
    return _replace_parent(model_input, crs_inputs[0].name) if len(crs_inputs) == 1 else model_input


def _replace_parent(model_input: ModelInput, parent: str) -> ModelInput:
    return ModelInput(
        model_input.name, model_input.kind, model_input.description, model_input.default, model_input.optional, parent
    )


def _default(name: str, kind: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if kind in NUMERIC_INPUT_TYPES:
        if isinstance(value, bool):
            raise ValueError(f"Input '{name}' is a {kind}; its default must be a number.")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Input '{name}' is a {kind}; its default must be a number, not {value!r}.") from None
    return str(value)


def _objects(raw: Any, what: str, allow_empty: bool = False) -> list[dict[str, Any]]:
    if raw is None:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{what} must be a list of objects.")
    if not raw and not allow_empty:
        raise ValueError(f"The model needs at least one entry in {what}.")
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Every entry of {what} must be an object, not {item!r}.")
    return list(raw)


def _parameter_key(name: str) -> str:
    return re.sub(r"\W+", "_", name.strip().lower())


def _text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()
