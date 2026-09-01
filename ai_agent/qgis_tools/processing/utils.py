from typing import Any

from qgis.core import (
    QgsApplication,
    QgsMapLayer,
    QgsProcessingParameterDefinition,
    QgsProject,
)

from ai_agent.qgis_tools.common.layers import find_layer_by_name

DESTINATION_TYPES = {
    "filedestination",
    "folderdestination",
    "pointclouddestination",
    "rasterdestination",
    "sink",
    "vectordestination",
    "vectortiledestination",
}
LAYER_PARAMETER_TYPES = {
    "annotation",
    "layer",
    "maplayer",
    "mesh",
    "multilayer",
    "multiplelayers",
    "pointcloud",
    "raster",
    "source",
    "vector",
}
TEMPORARY_OUTPUT = "TEMPORARY_OUTPUT"
PRIMARY_OUTPUT_KEY = "OUTPUT"


def get_registry() -> Any:
    registry = QgsApplication.processingRegistry()
    if registry is None:
        raise RuntimeError("The Processing registry is not available. Check that the Processing plugin is enabled.")
    return registry


_SEARCH_INDEX: list[tuple[Any, dict[str, str]]] = []
_INDEXED_COUNT = [-1]


def build_search_index() -> list[tuple[Any, dict[str, str]]]:
    algorithms = get_registry().algorithms()
    if _INDEXED_COUNT[0] != len(algorithms):
        _SEARCH_INDEX[:] = [(algorithm, _haystack(algorithm)) for algorithm in algorithms]
        _INDEXED_COUNT[0] = len(algorithms)
    return _SEARCH_INDEX


def _haystack(algorithm) -> dict[str, str]:
    try:
        tags = " ".join(algorithm.tags())
    except Exception:
        tags = ""
    identifier = (algorithm.id() or "").lower()
    return {
        "name": (algorithm.displayName() or "").lower(),
        "id": identifier,
        "bare": identifier.split(":")[-1],
        "tags": tags.lower(),
        "group": (algorithm.group() or "").lower(),
    }


def find_algorithm(algorithm_id: str) -> Any:
    wanted = (algorithm_id or "").strip()
    if not wanted:
        raise ValueError("No algorithm identifier was given.")
    algorithm = get_registry().algorithmById(wanted)
    if algorithm is None:
        raise ValueError(f"Algorithm not found: {wanted}. Look the exact identifier up with search_processing.")
    return algorithm


def algorithm_brief(algorithm) -> dict[str, Any]:
    return {
        "id": algorithm.id(),
        "name": algorithm.displayName(),
        "group": algorithm.group(),
        "summary": (algorithm.shortDescription() or "").strip(),
    }


def is_optional(parameter: QgsProcessingParameterDefinition) -> bool:
    try:
        return bool(parameter.flags() & QgsProcessingParameterDefinition.Flag.FlagOptional)
    except Exception:
        return False


def parameter_options(parameter) -> list[str]:
    try:
        options = parameter.options()
    except AttributeError:
        return []
    return [str(option) for option in options] if options else []


def describe_parameter(parameter: QgsProcessingParameterDefinition) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": parameter.name(),
        "description": parameter.description(),
        "type": parameter.type(),
        "optional": is_optional(parameter),
    }
    default = _default_value(parameter)
    if default is not None:
        info["default"] = default
    options = parameter_options(parameter)
    if options:
        info["options"] = [{"value": index, "label": label} for index, label in enumerate(options)]
        info["value_hint"] = "Pass the number from the value field, not the text from label."
    return info


def _default_value(parameter) -> Any:
    try:
        default = parameter.defaultValue()
    except Exception:
        return None
    return default if isinstance(default, (str, int, float, bool)) else None


def coerce_parameters(algorithm, arguments: dict[str, Any]) -> dict[str, Any]:
    result = dict(arguments)
    for parameter in algorithm.parameterDefinitions():
        name = parameter.name()
        param_type = str(parameter.type()).lower()
        if param_type == "enum" and name in result:
            result[name] = _coerce_enum(parameter, result[name])
        elif param_type in LAYER_PARAMETER_TYPES and name in result:
            result[name] = _coerce_layer_reference(result[name])
        elif param_type in DESTINATION_TYPES and name not in result and not is_optional(parameter):
            result[name] = TEMPORARY_OUTPUT
    return result


def destination_parameter_names(algorithm: Any) -> list[str]:
    return [parameter.name() for parameter in algorithm.parameterDefinitions() if _is_destination(parameter)]


def _is_destination(parameter: Any) -> bool:
    try:
        if parameter.isDestination():
            return True
    except Exception:
        pass
    return str(parameter.type()).lower() in DESTINATION_TYPES


def _coerce_layer_reference(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_coerce_layer_reference(item) for item in value]
    if isinstance(value, QgsMapLayer):
        return value.id()
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip()
    layer = QgsProject.instance().mapLayer(text)
    if layer is not None:
        return layer.id()
    try:
        layer = find_layer_by_name(text)
    except ValueError as failure:
        if "ambiguous" in str(failure).lower():
            raise
        return value
    return layer.id()


def _coerce_enum(parameter, value: Any) -> Any:
    options = parameter_options(parameter)
    if not options:
        return value
    if isinstance(value, list):
        return [_coerce_enum_value(options, item) for item in value]
    return _coerce_enum_value(options, value)


def _coerce_enum_value(options: list[str], value: Any) -> Any:
    if isinstance(value, (bool, int)):
        return value
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    lowered = text.lower()
    for index, option in enumerate(options):
        if option.lower() == lowered:
            return index
    return value


def resolve_layer(value: Any) -> QgsMapLayer | None:
    if isinstance(value, QgsMapLayer):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    by_id = QgsProject.instance().mapLayer(value.strip())
    if by_id is not None:
        return by_id
    try:
        return find_layer_by_name(value)
    except ValueError:
        return None


def apply_output_name(result: dict[str, Any], output_name: str) -> str:
    name = (output_name or "").strip()
    if not name or not isinstance(result, dict):
        return ""
    keys = [PRIMARY_OUTPUT_KEY] + [key for key in result if key != PRIMARY_OUTPUT_KEY]
    for key in keys:
        layer = resolve_layer(result.get(key))
        if layer is not None:
            layer.setName(name)
            return name
    return ""


def normalize_output(value: Any) -> Any:
    if isinstance(value, QgsMapLayer):
        return {"layer_name": value.name(), "layer_id": value.id()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [normalize_output(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_output(item) for key, item in value.items()}
    return str(value)
