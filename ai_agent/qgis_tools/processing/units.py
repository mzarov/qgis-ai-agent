from typing import Any

from ai_agent.qgis_tools.common.layers import crs_is_geographic, suggest_metric_crs
from ai_agent.qgis_tools.processing.utils import resolve_layer

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
        raise ValueError(_degrees_error(arguments[parent_name], layer, parameter.name(), distance, parent_name))


def _degrees_error(layer_name, layer, parameter_name: str, distance: float, parent_name: str) -> str:
    target_crs = suggest_metric_crs(layer)
    output_name = f"{layer_name} {target_crs.replace('EPSG:', 'UTM ')}"
    return (
        f"Layer '{layer_name}' is in a geographic CRS ({layer.crs().authid()}), "
        f"whose unit is the degree, not the metre. The value {parameter_name}={distance} "
        f"would be read as {distance} degrees and give a meaningless result.\n"
        "Add a reprojection before this step and run the processing on its result:\n"
        f'run_processing(algorithm_id="native:reprojectlayer", '
        f'parameters={{"INPUT": "{layer_name}", "TARGET_CRS": "{target_crs}"}}, '
        f'output_name="{output_name}")\n'
        f"then repeat the current call with '{output_name}' in {parent_name}.\n"
        f"If {distance} really was meant in degrees, say so to the user."
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
