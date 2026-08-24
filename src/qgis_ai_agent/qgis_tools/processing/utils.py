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
# Расстояние больше этого на географической CRS почти наверняка задано в метрах:
# 1 градус — это уже около 111 км, легитимные буферы в градусах заметно меньше.
SUSPICIOUS_DEGREES = 1.0


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


def check_distance_units(algorithm, arguments: dict[str, Any]) -> None:
    """
    Ловит классическую ошибку: расстояние в метрах на слое с географической CRS.
    В EPSG:4326 единица — градус, поэтому DISTANCE=500 даёт буфер в 500 градусов
    и вырожденную геометрию вместо результата. Молча исправлять нельзя —
    выбор между перепроецированием и градусами за пользователем.
    """
    from qgis.core import QgsProject

    for parameter in algorithm.parameterDefinitions():
        if parameter.type() != "distance":
            continue
        value = arguments.get(parameter.name())
        try:
            distance = float(value)
        except (TypeError, ValueError):
            continue
        if distance <= SUSPICIOUS_DEGREES:
            continue

        layer_name = arguments.get(_parent_parameter_name(parameter))
        if not isinstance(layer_name, str):
            continue
        layers = QgsProject.instance().mapLayersByName(layer_name.strip())
        if not layers or not _is_geographic(layers[0]):
            continue

        raise ValueError(
            f"Слой «{layer_name}» в географической CRS ({layers[0].crs().authid()}), "
            f"её единица — градус, а не метр. Значение {parameter.name()}={distance} "
            f"будет истолковано как {distance} градусов и даст бессмысленный результат. "
            "Сначала перепроецируйте слой в метрическую CRS "
            "(алгоритм native:reprojectlayer, например в UTM или EPSG:3857) "
            "и запустите обработку на результате. "
            f"Если {distance} действительно задано в градусах — так и скажите пользователю."
        )


def _parent_parameter_name(parameter) -> str:
    """Имя параметра-слоя, к которому привязано расстояние."""
    try:
        return parameter.parentParameterName() or ""
    except AttributeError:
        return ""


def _is_geographic(layer) -> bool:
    """Является ли CRS слоя географической (единицы — градусы)."""
    try:
        return bool(layer.crs().isGeographic())
    except Exception:
        return False


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
