# Smoke Checklist

Ручная проверка в живом QGIS. Автотестов в проекте нет.

## Техническая проверка после правок

- `python3 -m compileall -q src/` — без ошибок.
- `python3 tools/check_names.py src/` — нет имён, использованных но не
  определённых. `compileall` такое пропускает: `NameError` срабатывает только
  при вызове, поэтому выпавший при рефакторинге импорт доживает до живого QGIS.
- Имена тулов в `skills/<домен>/SKILL.md` совпадают с реестром.

## Read-тулы без агента

Открыть проект со слоями, затем **Плагины → Консоль Python**:

```python
from qgis_ai_agent.qgis_tools.registry import execute_tool
execute_tool("get_project_info", {})
execute_tool("list_layers", {})
execute_tool("describe_layer", {"layer_name": "ИМЯ_СЛОЯ"})
execute_tool("get_field_values", {"layer_name": "ИМЯ_СЛОЯ", "field_name": "ПОЛЕ"})
execute_tool("sample_features", {"layer_name": "ИМЯ_СЛОЯ", "limit": 3})
execute_tool("query_layer", {"layer_name": "Дороги", "aggregate": "count"})
execute_tool("query_layer", {"layer_name": "Дороги", "aggregate": "count", "filter": "highway = 'motorway'"})
execute_tool("query_layer", {"layer_name": "Города", "order_by": "population DESC", "limit": 5, "fields": ["name", "population"]})
execute_tool("query_layer", {"layer_name": "Реки", "order_by": "$length DESC", "limit": 1})
execute_tool("query_layer", {"layer_name": "Озера и пруды", "aggregate": "sum", "expression": "$area"})
execute_tool("query_layer", {"layer_name": "Дороги", "aggregate": "mean", "expression": "$length", "group_by": "highway"})
execute_tool("describe_style", {"layer_name": "ИМЯ_СЛОЯ"})
execute_tool("get_qgis_info", {})
execute_tool("get_canvas_extent", {})
execute_tool("search_processing", {"query": "buffer"})
execute_tool("describe_processing", {"algorithm_id": "native:buffer"})
```

Ожидания:

- `get_project_info` отдаёт дерево слоёв с группами и видимостью, единицы, темы
- `describe_layer` для слоя в `EPSG:4326` отдаёт `crs_is_geographic: True`,
  `suggested_metric_crs`, а также `provider`, `is_valid` и `style_summary`
- `get_field_values` для числового поля отдаёт `min`/`max`, для текстового —
  список уникальных значений с пометкой об обрезке
- `sample_features` отдаёт реальные записи, длинные значения обрезаны
- `describe_style` показывает тип рендерера и классы с цветами
- `describe_processing` отдаёт enum парами `{"value": 0, "label": "Round"}`
- несуществующее имя слоя или поля даёт ошибку со списком доступных
- `query_layer` без `aggregate` отдаёт объекты, с `aggregate` — одно число
- `group_by` даёт список групп со значением и числом объектов в каждой
- `$length` и `$area` считаются в единицах CRS слоя: на слое в градусах
  число получится бессмысленным, агент обязан это сказать
- ошибка в выражении даёт текст парсера, а не падение

### Ветки классов в describe_style

Категории, градации и правила не проверить на проекте с одиночными символами.
Снипет подставляет категоризацию, проверяет и возвращает рендерер обратно —
в проекте ничего не остаётся:

```python
from qgis.core import QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol
from qgis_ai_agent.qgis_tools.registry import execute_tool

layer = QgsProject.instance().mapLayersByName("ИМЯ_СЛОЯ")[0]
saved = layer.renderer().clone()
field = layer.fields().names()[1]
values = list(layer.uniqueValues(layer.fields().indexOf(field)))[:4]
categories = [
    QgsRendererCategory(v, QgsSymbol.defaultSymbol(layer.geometryType()), str(v))
    for v in values
]
layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
print(execute_tool("describe_style", {"layer_name": "ИМЯ_СЛОЯ"}))
print(execute_tool("describe_layer", {"layer_name": "ИМЯ_СЛОЯ"})["style_summary"])
layer.setRenderer(saved)
```

Ожидания: `class_attribute`, список `classes` со значением, подписью и символом
на каждый класс, `style_summary` вида «категории по полю «…», классов: 4».

### Секреты в источнике

Если есть слой PostGIS — проверить, что пароль не утекает:

```python
execute_tool("describe_layer", {"layer_name": "ИМЯ_СЛОЯ_POSTGIS"})["source"]
```

В строке должно быть `password=‹скрыто›`, а не сам пароль.

## Агентный цикл

- **Чтение без подтверждения.** «что у меня в проекте?» → агент вызывает
  `list_layers`, отвечает по факту, кнопки подтверждения не появляются.
- **Данные из проекта.** «какие поля в слое X?» → `describe_layer`, в ответе
  реальные поля.
- **Формулировка до подтверждения.** Агент пишет «предлагаю», а не «я создал».
- **Отмена.** Нажать «Отмена» → в проекте ничего не изменилось.
- **Ошибка тула не рвёт прогон.** Запрос с несуществующим слоем → агент видит
  ошибку и исправляется сам.
- **Лимит ходов.** Заведомо неподъёмная задача → остановка на `MAX_ITERATIONS`
  с внятным сообщением, QGIS не виснет.

## Скиллы

- Вопрос про слои не требует `load_skill` — `inspect` предзагружен.
- Запрос про обработку → в логе видно `Загружен скилл: processing`.
- Вопрос про цвета и оформление → `Загружен скилл: style`.
- Скилл загружается один раз за прогон.

## Сбор контекста

- «расскажи про мой проект» → `get_project_info`, в ответе группы слоёв,
  что включено, единицы измерения
- «какие значения в поле X» → `get_field_values`, реальные значения
- «почему города красные» → `load_skill(style)` → `describe_style`, ответ
  называет поле классификации и цвет, а не просто «красные»
- битый слой (переименовать исходный файл) → `describe_layer` отдаёт
  `is_valid: false`, агент предупреждает, а не строит планы поверх

## Обработка и проверка CRS

Главный сценарий, ради которого сделана валидация до очереди:

1. «построй буфер 500 м вокруг городов» на слое в `EPSG:4326`
2. первый `run_processing` отклоняется — шаг помечен ✕ в чате
3. агент **не останавливается**: читает ошибку и строит план из двух шагов —
   `native:reprojectlayer` → `native:buffer` на его результате
4. после подтверждения в проекте появляются оба слоя, буфер геометрически верный

Дополнительно:

- «найди алгоритм буфера» → `search_processing` возвращает `native:buffer`
- enum передан подписью вместо индекса → тул сам приводит к индексу

## Транспорт

- **Эндпоинт с function calling** — работает нативный путь.
- **Эндпоинт без него** — первый запрос падает на `tools`, адаптер уходит в
  JSON-протокол, флаг `supports_tools` записывается, следующие запросы сразу
  идут по JSON-пути.
- Смена URL в настройках не ломает выбор: флаг хранится по хешу URL.

```python
from qgis_ai_agent.core.settings import get_api_url, get_supports_tools
get_supports_tools(get_api_url())
```

## Потоки и выгрузка

- UI не подвисает во время многошагового прогона.
- Во время применения батча кнопка «Отправить» заблокирована, в чате видно
  прогресс по шагам.
- Выгрузка плагина при активном запросе не роняет QGIS.
