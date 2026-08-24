# qgis_tools/ — руки агента

Вся PyQGIS-логика исполнения. Один тул — один класс — один файл, до 200 строк.

## Контракт тула

```python
class DescribeLayerTool(BaseTool):
    """Однострочное описание по-русски."""
    name = "describe_layer"            # snake_case, уникально в реестре
    description = "..."                # по-русски, попадает в схему для модели
    skill = "inspect"                  # домен: с каким скиллом грузится тул
    safety = SAFETY_READ               # read | write | destructive
    capabilities = ["project:layer:describe"]
    examples = ["Какие поля в слое дорог?"]
    constraints = ["Слой должен существовать"]
    params_schema = [
        {"name": "layer_name", "type": "string", "description": "...", "required": True},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Человекочитаемая строка для чата."""

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Выполняет вызов. params — словарь аргументов от модели."""
```

`get_openai_schema()` строится из `params_schema` автоматически — руками схему
не писать. Поддерживаемые `type`: `string`, `number`, `integer`, `boolean`,
`array`, `object`; необязательный `enum` перечисляет допустимые значения.

## Правила

1. **`skill` и `safety` обязательны.** Без `skill` тул не попадёт ни в один набор.
   `safety` по умолчанию `write` — для читающего тула ставь `SAFETY_READ` явно.
2. **`read` не имеет права ничего менять.** Он выполняется без подтверждения
   пользователя. Любая мутация проекта — это `write`, даже безобидная.
3. **`summarize_call` описывает вызов по-русски.** Знание о том, как выглядит шаг,
   живёт в туле, а не в реестре. Не указанные пользователем координаты показывай
   как «авто», а не подставляй выдуманные значения по умолчанию.
4. **Ошибки — с внятным текстом на русском и подсказкой.** Модель их читает и
   исправляется. Если объект не найден, приложи список доступных
   (см. `inspect/utils.py::find_layer_by_name`).
5. **Переиспользуй общие хелперы.** `layout/utils.py` уже умеет зоны страницы,
   clamp по границам и anti-overlap; `inspect/utils.py` — описания слоёв и CRS.
   Не дублируй.
6. **Результат должен сериализоваться в JSON.** Объекты PyQGIS отдавай как имена
   или идентификаторы (см. `processing/utils.py::normalize_output`).
7. **Регистрация:** класс → `<домен>/__init__.py` в список домена → импорт списка
   в `registry.py`. Плюс `skills/<домен>/SKILL.md` с тем же именем тула в `tools`.

## PyQGIS — не галлюцинировать

1. Цель — QGIS 4.0. API QGIS 2.x не существует (никакого `QgsComposition`).
2. Состояние проекта — всегда через `QgsProject.instance()`.
3. Макеты: `QgsLayout`, `QgsLayoutItemMap`, `QgsLayoutItemLegend`,
   `QgsLayoutItemScaleBar`, `QgsLayoutItemLabel`.
4. Обработка: `QgsApplication.processingRegistry()`, модуль `processing`.
5. `try/except` вокруг рискованного, лог через
   `QgsMessageLog.logMessage(msg, "QGIS AI Agent", Qgis.Info)`.
6. Импорты вверху, абсолютные. Без `# -*- coding: utf-8 -*-` и без docstring
   на уровне модуля.

## Когда домен безграничен

Если операций в домене сотни (как алгоритмы Processing), не пиши класс на каждую.
Дай три тула — поиск, описание сигнатуры, запуск — и опиши в `SKILL.md`, как ими
пользоваться. Образец: `processing/`.
