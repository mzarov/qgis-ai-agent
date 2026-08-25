from typing import Any

from qgis_ai_agent.qgis_tools.inspect.utils import crs_is_geographic, suggest_metric_crs
from qgis_ai_agent.qgis_tools.processing.utils import resolve_layer

SUSPICIOUS_DEGREES = 1.0


def check_distance_units(algorithm, arguments: dict[str, Any]) -> None:
    for parameter in algorithm.parameterDefinitions():
        if parameter.type() != "distance":
            continue
        distance = _as_float(arguments.get(parameter.name()))
        if distance is None or distance <= SUSPICIOUS_DEGREES:
            continue
        parent_name = _parent_parameter_name(parameter)
        layer = resolve_layer(arguments.get(parent_name))
        if layer is None or not crs_is_geographic(layer):
            continue
        raise ValueError(
            _degrees_error(arguments[parent_name], layer, parameter.name(), distance, parent_name)
        )


def _degrees_error(layer_name, layer, parameter_name: str, distance: float, parent_name: str) -> str:
    target_crs = suggest_metric_crs(layer)
    output_name = f"{layer_name} {target_crs.replace('EPSG:', 'UTM ')}"
    return (
        f"Слой «{layer_name}» в географической CRS ({layer.crs().authid()}), "
        f"её единица — градус, а не метр. Значение {parameter_name}={distance} "
        f"будет истолковано как {distance} градусов и даст бессмысленный результат.\n"
        "Добавьте перед этим шагом перепроецирование и запустите обработку на его результате:\n"
        f'run_processing(algorithm_id="native:reprojectlayer", '
        f'parameters={{"INPUT": "{layer_name}", "TARGET_CRS": "{target_crs}"}}, '
        f'output_name="{output_name}")\n'
        f"затем повторите текущий вызов, подставив «{output_name}» в {parent_name}.\n"
        f"Если {distance} действительно задано в градусах — так и скажите пользователю."
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parent_parameter_name(parameter) -> str:
    try:
        return parameter.parentParameterName() or ""
    except AttributeError:
        return ""
