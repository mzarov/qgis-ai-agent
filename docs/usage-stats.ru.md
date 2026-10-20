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
- настроена ли модель в настройках, только да или нет;
- число прогонов и применённых пакетов (день, когда плагин был загружен,
  считается и без них);
- сколько раз вызывался и завершался ошибкой каждый инструмент плагина,
  загружался каждый встроенный навык и случался каждый вид сбоя. Имя,
  придуманное моделью, и имена ваших собственных навыков не отправляются.

День без связи отправляется позже; ждут последние три таких дня.

Ничего из проекта не отправляется: ни слои, ни поля, ни значения, ни
координаты, ни пути к файлам. Ваши запросы, ответы модели, ключи, адреса и
имена моделей тоже не отправляются.

## Как это хранится

Сборщик хранит SHA-256-хеш идентификатора установки, одну строку на установку
в день. IP-адреса не сохраняются, журналы запросов не ведутся; адрес, с
которого пришёл отчёт, нужен только для ограничения числа отчётов с него в
минуту. Публикуются только итоговые суммы, а значение вроде версии, языка
или имени инструмента показывается, только когда о нём сообщили хотя бы
5 установок. Код лежит в
[`telemetry/worker`](https://github.com/mzarov/qgis-ai-agent/tree/main/telemetry/worker).

## Цифры

Графики по дням заканчиваются вчерашним днём, по неделям — прошлой неделей;
последние дни ещё могут подрасти. Наведите курсор на столбец или точку, чтобы
увидеть значение; каждый график открывается и таблицей.

| Показатель | Значение |
| --- | --- |
| Установок за всё время | <span data-usage-stat="installs_total">—</span> |
| Активных установок за 30 дней | <span data-usage-stat="installs_30d">—</span> |
| Запусков за 30 дней | <span data-usage-stat="runs_30d">—</span> |
| Применённых батчей за 30 дней | <span data-usage-stat="applies_30d">—</span> |
| Скачиваний с plugins.qgis.org за всё время | <span data-usage-stat="downloads_total">—</span> |
| Скачиваний с plugins.qgis.org за 30 дней | <span data-usage-stat="downloads_30d" data-format="{0} с {1}">—</span> |
| Установки, активные через 7+ дней после первого дня | <span data-usage-stat="kept_7" data-format="{0} ({1} из {2})">—</span> |
| Установки, активные через 30+ дней после первого дня | <span data-usage-stat="kept_30" data-format="{0} ({1} из {2})">—</span> |

<div id="usage-stats" data-loading="Загружаем статистику…" data-failed="Не удалось загрузить статистику. Попробуйте позже." data-empty="Данных пока нет." data-table="Показать таблицей">
<p class="usage-stats-status" role="status">Для графиков нужен JavaScript.</p>
<figure class="usage-chart" data-chart="funnel" data-title="Воронка: установки, активные за 30 дней" data-key="Шаг" data-value="Установки" data-share="Доля от активных" data-active="Активные" data-configured="Настроили модель" data-ran="Запускали агента" data-applied="Применяли пакет"></figure>
<figure class="usage-chart" data-chart="installs" data-title="Активные установки по дням, последние 90 дней" data-key="День" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="runs" data-title="Запуски по дням, последние 90 дней" data-key="День" data-value="Запуски"></figure>
<figure class="usage-chart" data-chart="new" data-title="Новые установки по неделям, последние 12 недель" data-key="Неделя с" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="returning" data-title="Вернувшиеся установки по неделям, последние 12 недель" data-key="Неделя с" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="plugin" data-title="Версии плагина, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="Версии QGIS, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="tools" data-title="15 самых вызываемых инструментов за 30 дней" data-key="Инструмент" data-value="Вызовы"></figure>
<figure class="usage-chart" data-chart="tool_errors" data-title="15 инструментов с наибольшим числом ошибок и доля ошибок за 30 дней" data-key="Инструмент" data-value="Ошибки" data-calls="Вызовы" data-rate="Доля ошибок"></figure>
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

Недели начинаются с понедельника; вернувшаяся установка была активна и в одну
из прошлых недель. Плагин 0.4.0 не сообщает о настройке модели и об ошибках
вызовов, поэтому воронка считает его установки, запускавшие агента,
настроенными, а доля ошибок не учитывает его вызовы. Скачивания включают
обновления.
