---
name: processing
description: Run QGIS geoprocessing algorithms — buffers, clips, joins, reprojection, statistics, raster maths. Load this for any request that transforms or analyses data.
tools: [search_processing, describe_processing, run_processing]
---

# Geoprocessing

QGIS ships over a thousand algorithms. You are not expected to know their
identifiers or signatures — discover them at runtime.

## The three-step rule

Never call `run_processing` from memory. Always:

1. `search_processing` with words describing the task → returns candidate ids
   such as `native:buffer`. **Search in English** — algorithm ids, tags and groups
   are English even when the QGIS interface is localised. Searching in Russian
   usually returns nothing and costs a wasted round trip.
2. `describe_processing` with the chosen id → returns the exact parameter names,
   types, whether each is optional, and the allowed values for enums.
3. `run_processing` with those exact parameter names.

Guessing a parameter name produces a failed run and a confusing error for the
user. One extra read call is much cheaper than a wrong write.

## The map most requests land on

Search still needs the right English words, and a few everyday tasks are not
algorithms at all. Start from this table, then confirm with `describe_processing`
— the ids below are stable QGIS core, but the parameters are not worth guessing.

**Vector overlay**

| Задача | id |
|---|---|
| обрезать слой по границе другого | `native:clip` |
| пересечение двух слоёв | `native:intersection` |
| объединение с сохранением атрибутов | `native:union` |
| вычесть один слой из другого | `native:difference` |
| склеить несколько слоёв в один | `native:mergevectorlayers` |
| растворить границы, сгруппировав по полю | `native:dissolve` |

**Геометрия**

| Задача | id |
|---|---|
| буфер | `native:buffer` |
| центроиды полигонов | `native:centroids` |
| выпуклая оболочка | `native:convexhull` |
| упростить геометрию | `native:simplifygeometries` |
| починить битую геометрию | `native:fixgeometries` |
| сменить проекцию слоя | `native:reprojectlayer` |
| разбить мультичасти на отдельные объекты | `native:multiparttosingleparts` |
| полигоны Вороного | `native:voronoipolygons` |

**Атрибуты и связи**

| Задача | id |
|---|---|
| добавить или пересчитать поле | `native:fieldcalculator` |
| присоединить таблицу по общему полю | `native:joinattributestable` |
| присоединить по расположению | `native:joinattributesbylocation` |
| присоединить ближайший объект | `native:joinbynearest` |
| оставить или переименовать поля | `native:refactorfields` |
| статистика по группам | `qgis:statisticsbycategories` |
| сколько точек в каждом полигоне | `native:countpointsinpolygon` |

**Выборка**

| Задача | id |
|---|---|
| отобрать по условию | `native:extractbyexpression` |
| отобрать по расположению | `native:extractbylocation` |
| отобрать по охвату | `native:extractbyextent` |

**Растр**

| Задача | id |
|---|---|
| растровый калькулятор | `native:rastercalc` |
| обрезать растр по маске | `gdal:cliprasterbymasklayer` |
| сменить проекцию растра | `gdal:warpreproject` |
| склеить растры | `gdal:merge` |
| уклон, экспозиция, отмывка | `native:slope`, `native:aspect`, `native:hillshade` |
| изолинии | `gdal:contour` |
| статистика растра по полигонам | `native:zonalstatisticsfb` |
| снять значения растра в точках | `native:rastersampling` |
| растр в полигоны | `gdal:polygonize` |
| векторы в растр | `gdal:rasterize` |

## Что алгоритмами не делается

Три самых частых запроса — не алгоритмы, и поиск на них уводит не туда.
`search_processing("area")` первым отдаёт `native:serviceareafrompoint`, то есть
зону транспортной доступности, а вовсе не площадь.

Площадь, длина, периметр, координаты — это **выражения**, а не алгоритмы:

- посчитать и записать в поле — `native:fieldcalculator` с `FORMULA`
- просто узнать значение, ничего не меняя — `query_layer` из скилла `inspect`

| Нужно | Выражение |
|---|---|
| площадь полигона | `$area` |
| длина линии, периметр | `$length`, `$perimeter` |
| координаты точки | `$x`, `$y` |
| площадь в гектарах | `$area / 10000` |

Единицы `$area` и `$length` — это единицы CRS слоя. На географической системе
получатся квадратные градусы, что бессмысленно: сначала `native:reprojectlayer`
в метрическую CRS, потом счёт.

NDVI и прочая арифметика по каналам — тоже не отдельный алгоритм, а
`native:rastercalc` с выражением вида `("снимок@4" - "снимок@3") / ("снимок@4" + "снимок@3")`,
где `@N` — номер канала, а имя перед `@` — имя слоя в проекте.

У растрового калькулятора есть подвох: `EXTENT`, `CELL_SIZE` и `CRS` обязательны,
и взять их неоткуда, кроме исходного растра. Сначала `describe_layer` по нему —
оттуда `extent` и `crs`, — и только потом запуск. Размер ячейки берите из
`describe_layer` того же растра, а не выдумывайте: чужое значение молча
пересемплирует результат.

## Parameters

- Input layers are given by their project layer name. Confirm the name with
  `list_layers` first — names are case-sensitive.
- **Enum parameters take a number, not a label.** `describe_processing` returns
  them as `{"value": 0, "label": "Round"}` pairs — pass the `value`.
- For an output that should become a new layer, pass `'TEMPORARY_OUTPUT'` unless
  the user asked for a file on disk.

## Metres on a geographic CRS

`list_layers` and `describe_layer` report `crs_is_geographic`. When it is true the
layer measures in degrees, and a distance in metres is meaningless — 500 there
means 500 degrees.

Do not hand this back to the user as a problem. Fix it yourself with a two-step plan:

```
run_processing(algorithm_id="native:reprojectlayer",
               parameters={"INPUT": "Города", "TARGET_CRS": "EPSG:32641"},
               output_name="Города UTM 41")
run_processing(algorithm_id="native:buffer",
               parameters={"INPUT": "Города UTM 41", "DISTANCE": 500},
               output_name="Буфер 500 м")
```

`describe_layer` returns `suggested_metric_crs` for exactly this — use it as
`TARGET_CRS` rather than picking a CRS yourself. If you queue a metric distance on
a geographic layer anyway, the step is rejected and the error tells you the same
thing; act on it instead of reporting it.

## Chaining steps

A queued step has not run yet, so its output layer does not exist while you are
planning. Give each step an `output_name` and reference that name in the next
step — this is the only reliable way to chain two runs in one plan.

Queue **every** step of the chain in the same turn. Writing out "сначала
перепроецируем, потом построим буфер" and stopping there leaves the user with
nothing to confirm — the plan only exists once `run_processing` has been called
for each step.

## Results

`run_processing` loads its output into the project by default, so the new layer
becomes available to later steps. Pass `load_output: false` only when the user
explicitly wants the result not added.
