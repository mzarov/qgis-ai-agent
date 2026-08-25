from typing import Any

from qgis.core import (
    QgsApplication,
    QgsMapLayer,
    QgsProcessingParameterDefinition,
    QgsProject,
)

from qgis_ai_agent.qgis_tools.common.layers import find_layer_by_name

DESTINATION_TYPES = {
    "sink",
    "vectorDestination",
    "rasterDestination",
    "fileDestination",
    "folderDestination",
}
TEMPORARY_OUTPUT = "TEMPORARY_OUTPUT"
PRIMARY_OUTPUT_KEY = "OUTPUT"


def get_registry():
    registry = QgsApplication.processingRegistry()
    if registry is None:
        raise RuntimeError(
            "Реестр Processing недоступен. Проверьте, что модуль Processing включён."
        )
    return registry


_SEARCH_INDEX: list[tuple[Any, dict[str, str]]] = []


def build_search_index() -> list[tuple[Any, dict[str, str]]]:
    if not _SEARCH_INDEX:
        _SEARCH_INDEX.extend(
            (algorithm, _haystack(algorithm)) for algorithm in get_registry().algorithms()
        )
    return _SEARCH_INDEX


def _haystack(algorithm) -> dict[str, str]:
    try:
        tags = " ".join(algorithm.tags())
    except Exception:
        tags = ""
    return {
        "name": (algorithm.displayName() or "").lower(),
        "id": (algorithm.id() or "").lower(),
        "tags": tags.lower(),
        "group": (algorithm.group() or "").lower(),
    }


def find_algorithm(algorithm_id: str):
    wanted = (algorithm_id or "").strip()
    if not wanted:
        raise ValueError("Не указан идентификатор алгоритма.")
    algorithm = get_registry().algorithmById(wanted)
    if algorithm is None:
        raise ValueError(
            f"Алгоритм не найден: {wanted}. "
            "Найдите точный идентификатор через search_processing."
        )
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
        return bool(parameter.flags() & QgsProcessingParameterDefinition.FlagOptional)
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
        info["options"] = [
            {"value": index, "label": label} for index, label in enumerate(options)
        ]
        info["value_hint"] = "Передавайте число из поля value, а не текст из label."
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
        param_type = parameter.type()
        if param_type == "enum" and name in result:
            result[name] = _coerce_enum(parameter, result[name])
        elif (
            param_type in DESTINATION_TYPES
            and name not in result
            and not is_optional(parameter)
        ):
            result[name] = TEMPORARY_OUTPUT
    return result


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
