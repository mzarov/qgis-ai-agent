from typing import Any

from qgis.core import QgsApplication, QgsMapLayer, QgsProcessingParameterDefinition

# Типы параметров-выходов: если такой обязателен и не задан, подставляем временный слой.
DESTINATION_TYPES = {
    "sink",
    "vectorDestination",
    "rasterDestination",
    "fileDestination",
    "folderDestination",
}
TEMPORARY_OUTPUT = "TEMPORARY_OUTPUT"


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
    # Для перечислений QGIS ждёт ИНДЕКС варианта, а не его название.
    # Отдаём пары value/label, иначе модель передаёт строку и алгоритм её отвергает.
    options = _parameter_options(parameter)
    if options:
        info["options"] = [
            {"value": index, "label": label} for index, label in enumerate(options)
        ]
        info["value_hint"] = "Передавайте число из поля value, а не текст из label."
    return info


def _parameter_options(parameter) -> list[str]:
    """Варианты enum-параметра в виде списка подписей."""
    try:
        options = parameter.options()
    except AttributeError:
        return []
    return [str(option) for option in options] if options else []


def coerce_parameters(algorithm, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Правит частые расхождения между тем, что присылает модель, и тем, что ждёт QGIS:
    названия enum-вариантов переводит в индексы, обязательные выходы заполняет
    временным слоем. Неизвестные значения не трогает — пусть алгоритм сам ругнётся.
    """
    result = dict(arguments)
    for parameter in algorithm.parameterDefinitions():
        name = parameter.name()
        param_type = parameter.type()
        if param_type == "enum" and name in result:
            result[name] = _coerce_enum(parameter, result[name])
        elif param_type in DESTINATION_TYPES and name not in result and not is_optional(parameter):
            result[name] = TEMPORARY_OUTPUT
    return result


def _coerce_enum(parameter, value: Any) -> Any:
    """Переводит название варианта enum в индекс, сохраняя списки для множественного выбора."""
    options = _parameter_options(parameter)
    if not options:
        return value
    if isinstance(value, list):
        return [_coerce_enum_value(options, item) for item in value]
    return _coerce_enum_value(options, value)


def _coerce_enum_value(options: list[str], value: Any) -> Any:
    """Один вариант enum: индекс оставляем как есть, подпись ищем в списке."""
    # bool наследует int, поэтому проверяем его первым.
    if isinstance(value, bool) or isinstance(value, int):
        return value
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    lowered = text.lower()
    for index, option in enumerate(options):
        if option.lower() == lowered:
            return index
    return value


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
