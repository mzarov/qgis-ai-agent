from typing import Any

from qgis.core import QgsApplication, QgsMapLayer, QgsProcessingParameterDefinition


def get_registry():
    """Возвращает реестр алгоритмов обработки QGIS."""
    registry = QgsApplication.processingRegistry()
    if registry is None:
        raise RuntimeError("Реестр Processing недоступен. Проверьте, что модуль Processing включён.")
    return registry


def find_algorithm(algorithm_id: str):
    """Находит алгоритм по идентификатору вида native:buffer."""
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
    """Краткая карточка алгоритма для результатов поиска."""
    return {
        "id": algorithm.id(),
        "name": algorithm.displayName(),
        "group": algorithm.group(),
        "summary": (algorithm.shortDescription() or "").strip(),
    }


def is_optional(parameter: QgsProcessingParameterDefinition) -> bool:
    """Является ли параметр алгоритма необязательным."""
    try:
        return bool(parameter.flags() & QgsProcessingParameterDefinition.FlagOptional)
    except Exception:
        return False


def describe_parameter(parameter: QgsProcessingParameterDefinition) -> dict[str, Any]:
    """Описание одного параметра алгоритма для модели."""
    info: dict[str, Any] = {
        "name": parameter.name(),
        "description": parameter.description(),
        "type": parameter.type(),
        "optional": is_optional(parameter),
    }
    try:
        default = parameter.defaultValue()
        if default is not None and isinstance(default, (str, int, float, bool)):
            info["default"] = default
    except Exception:
        pass
    # Для перечислений показываем допустимые варианты — иначе модель их не угадает.
    try:
        options = parameter.options()
        if options:
            info["options"] = [str(option) for option in options]
    except AttributeError:
        pass
    return info


def normalize_output(value: Any) -> Any:
    """Приводит результат алгоритма к сериализуемому виду."""
    if isinstance(value, QgsMapLayer):
        return {"layer_name": value.name(), "layer_id": value.id()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [normalize_output(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_output(item) for key, item in value.items()}
    return str(value)
