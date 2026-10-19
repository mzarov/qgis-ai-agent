# Статистика использования

AI Agent отправляет анонимную статистику использования. По умолчанию она
включена; при первой загрузке плагин говорит об этом и предлагает её
выключить. Переключатель находится в Настройки → Приватность. На этой странице
итоги от всех установок, где статистика не выключена.

## Что отправляется

Не больше одного отчёта на установку в день:

- случайный идентификатор установки, созданный на вашем компьютере и ни с чем
  не связанный;
- дата без времени;
- версии плагина и QGIS, семейство ОС и язык интерфейса;
- локальный сервер модели или удалённый и его формат API;
- число прогонов и применённых пакетов;
- сколько раз вызывался каждый инструмент, загружался каждый навык и
  случался каждый вид сбоя.

Ничего из проекта не отправляется: ни слои, ни поля, ни значения, ни
координаты, ни пути к файлам. Ваши запросы, ответы модели, ключи, адреса и
имена моделей тоже не отправляются.

## Как это хранится

Сборщик хранит SHA-256-хеш идентификатора установки, одну строку на установку
в день. IP-адреса не сохраняются, журналы запросов не ведутся. Публикуются
только суммы по дням. Код лежит в
[`telemetry/worker`](https://github.com/mzarov/qgis-ai-agent/tree/main/telemetry/worker).

## Цифры

Графики по дням заканчиваются вчерашним днём, а последние дни ещё могут
подрасти. Наведите курсор на столбец или точку, чтобы увидеть значение;
каждый график открывается и таблицей.

| Показатель | Значение |
| --- | --- |
| Установок за всё время | <span data-usage-stat="installs_total">—</span> |
| Активных установок за 30 дней | <span data-usage-stat="installs_30d">—</span> |
| Запусков за 30 дней | <span data-usage-stat="runs_30d">—</span> |
| Применённых батчей за 30 дней | <span data-usage-stat="applies_30d">—</span> |

<div id="usage-stats" data-loading="Загружаем статистику…" data-failed="Не удалось загрузить статистику. Попробуйте позже." data-empty="Данных пока нет." data-table="Показать таблицей">
<p class="usage-stats-status" role="status">Для графиков нужен JavaScript.</p>
<figure class="usage-chart" data-chart="installs" data-title="Активные установки по дням, последние 90 дней" data-key="День" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="runs" data-title="Запуски по дням, последние 90 дней" data-key="День" data-value="Запуски"></figure>
<figure class="usage-chart" data-chart="plugin" data-title="Версии плагина, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="Версии QGIS, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="tools" data-title="15 самых вызываемых инструментов за 30 дней" data-key="Инструмент" data-value="Вызовы"></figure>
<figure class="usage-chart" data-chart="skills" data-title="15 самых загружаемых навыков за 30 дней" data-key="Навык" data-value="Загрузки"></figure>
<figure class="usage-chart" data-chart="failures" data-title="15 самых частых видов сбоев за 30 дней" data-key="Вид" data-value="Сбои"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="os" data-title="Операционные системы" data-key="Система" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="provider" data-title="Серверы моделей" data-key="Сервер" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="dialect" data-title="Диалекты API" data-key="Диалект" data-value="Установки"></figure>
</div>
<figure class="usage-chart" data-chart="locale" data-title="Языки интерфейса, установки за 30 дней" data-key="Язык" data-value="Установки"></figure>
</div>

Операционные системы, серверы моделей и диалекты API считают установки за
последние 30 дней. Установка, обновившаяся за месяц, попадает под обе версии.
