# Статистика использования

AI Agent отправляет анонимную статистику использования. По умолчанию она
включена; при первой загрузке плагин говорит об этом и предлагает её
выключить. Переключатель находится в Настройки → Приватность. На этой странице
итоги от всех установок, где статистика не выключена.

## Что отправляется

Сборщик хранит один отчёт на установку в день. Через минуту после изменения
счётчиков плагин отправляет день на текущий момент, и он заменяет прежний отчёт
за этот день. В отчёте:

- случайный идентификатор установки, созданный на вашем компьютере и ни с чем
  не связанный;
- дата без времени;
- версии плагина и QGIS, семейство ОС и язык интерфейса;
- локальный сервер модели или удалённый и его формат API;
- к какому известному сервису относится сервер модели, по фиксированному
  списку (например, OpenAI, OpenRouter, Ollama или LM Studio), иначе только
  «другой локальный» или «другой удалённый». Адрес и имя модели не
  отправляются никогда;
- настроена ли модель в настройках, только да или нет;
- число запросов, диалогов, повторов, проверок после применения и применённых
  пакетов (день, когда плагин был загружен, считается и без них);
- чем заканчиваются прогоны: ответом, сбоем, остановкой или пределом шагов
  или токенов; сколько из них шло в режиме «План» или «Авто»; и чем
  заканчиваются планы: показан, отменён, откачен или применён в режиме «Авто»;
- шаги, активное время и токены каждого прогона, запросы в каждом диалоге и
  запросы до применения — всё как счётчики в фиксированных диапазонах вроде
  «3–5 запросов» или «1–3 мин»;
- сколько раз вызывался и завершался ошибкой каждый инструмент плагина и
  загружался каждый встроенный навык. Имя, придуманное моделью, и имена ваших
  собственных навыков не отправляются;
- сколько прогонов завершилось сбоем, по видам: категория вроде таймаута или
  отклонённого ключа, иначе код HTTP-ответа с коротким кодом ошибки провайдера
  (например, `context_length_exceeded`) или имя класса ошибки с файлом и строкой
  плагина, где она возникла. Текст ошибки не отправляется.

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
увидеть значение; каждый график открывается и таблицей. Диалоги, концы
прогонов, режимы, планы, сервисы моделей и диапазоны по прогонам приходят
только от плагина 0.4.3 и новее; пока такие установки не отчитались, на этих
графиках нет данных.

<div id="usage-stats" data-loading="Загружаем статистику…" data-failed="Не удалось загрузить статистику. Попробуйте позже." data-empty="Данных пока нет." data-table="Показать таблицей" data-other_local="Другой локальный сервер" data-other_remote="Другой удалённый сервис">
<p class="usage-stats-status" role="status">Для графиков нужен JavaScript.</p>
<div class="usage-tiles">
<div class="usage-tile"><span class="usage-tile-label">Активные установки</span><span class="usage-tile-value" data-usage-stat="installs_30d">—</span><span class="usage-tile-note" data-usage-stat="installs_total" data-format="за 30 дней, {0} за всё время">за 30 дней</span></div>
<div class="usage-tile"><span class="usage-tile-label">Запросы</span><span class="usage-tile-value" data-usage-stat="requests_30d">—</span><span class="usage-tile-note">за 30 дней</span></div>
<div class="usage-tile"><span class="usage-tile-label">Диалоги</span><span class="usage-tile-value" data-usage-stat="sessions_30d">—</span><span class="usage-tile-note">за 30 дней, плагин 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Запросов на диалог</span><span class="usage-tile-value" data-usage-stat="requests_per_session">—</span><span class="usage-tile-note">в среднем, плагин 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Прогоны, закончившиеся ответом</span><span class="usage-tile-value" data-usage-stat="answered">—</span><span class="usage-tile-note" data-usage-stat="answered" data-format="прогоны: {1} из {2}, плагин 0.4.3+">плагин 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Применённые пакеты</span><span class="usage-tile-value" data-usage-stat="applies_30d">—</span><span class="usage-tile-note">за 30 дней</span></div>
<div class="usage-tile"><span class="usage-tile-label">Активны через 7 дней</span><span class="usage-tile-value" data-usage-stat="kept_7">—</span><span class="usage-tile-note" data-usage-stat="kept_7" data-format="установки: {1} из {2}">после первого дня</span></div>
<div class="usage-tile"><span class="usage-tile-label">Скачивания</span><span class="usage-tile-value" data-usage-stat="downloads_total">—</span><span class="usage-tile-note" data-usage-stat="downloads_30d" data-format="{0} с {1}">за всё время</span></div>
</div>
</div>

### Рост

<div class="usage-section">
<figure class="usage-chart" data-chart="installs" data-title="Активные установки по дням, последние 90 дней" data-key="День" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="weeks" data-title="Новые и вернувшиеся установки по неделям, последние 12 недель" data-key="Неделя с" data-new="Новые" data-returning="Вернувшиеся"></figure>
<figure class="usage-chart" data-chart="retention" data-title="Установки, активные после первого дня" data-key="Через" data-kept="Активны" data-installs="Установки" data-share="Доля" data-kept_7="7+ дней" data-kept_30="30+ дней" data-format="{0} ({1} из {2})"></figure>
<figure class="usage-chart" data-chart="downloads" data-title="Скачивания с plugins.qgis.org по дням" data-key="День" data-downloads="Скачивания"></figure>
</div>

### Активация

<div class="usage-section">
<figure class="usage-chart" data-chart="funnel" data-title="Воронка: установки, активные за 30 дней" data-key="Шаг" data-value="Установки" data-share="Доля от активных" data-active="Активные" data-configured="Настроили модель" data-ran="Запускали агента" data-applied="Применяли пакет"></figure>
<figure class="usage-chart" data-chart="activation" data-title="Дни от первого дня до каждого шага, установки, впервые замеченные за 90 дней" data-key="Шаг" data-configured="Настроили модель" data-ran="Запускали агента" data-applied="Применяли пакет" data-d0="В тот же день" data-d1="На следующий день" data-d2_7="2–7 дней" data-d8_plus="8+ дней" data-never="Пока нет"></figure>
</div>

### Использование

<div class="usage-section">
<figure class="usage-chart" data-chart="daily_use" data-title="Запросы и диалоги по дням, последние 90 дней" data-key="День" data-runs="Запросы" data-sessions="Диалоги"></figure>
<figure class="usage-chart" data-chart="run_kinds" data-title="Прогоны по видам за 30 дней" data-key="Вид" data-value="Прогоны" data-requests="Запросы" data-retries="Повторы" data-checks="Проверки после применения"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="session_requests" data-title="Диалоги по числу запросов" data-key="Запросы" data-value="Диалоги" data-share="Доля" data-r1="1" data-r2="2" data-r3_5="3–5" data-r6_10="6–10" data-r11_plus="11+"></figure>
<figure class="usage-chart" data-chart="to_apply" data-title="Запросы до применения" data-key="Запросы" data-value="Применения" data-share="Доля" data-r1="1" data-r2="2" data-r3_5="3–5" data-r6_10="6–10" data-r11_plus="11+"></figure>
</div>
<figure class="usage-chart" data-chart="modes" data-title="Прогоны в режимах «План» и «Авто» за 30 дней" data-key="Режим" data-value="Прогоны" data-share="Доля от всех прогонов" data-plan="План" data-auto="Авто"></figure>
</div>

### Качество

<div class="usage-section">
<figure class="usage-chart" data-chart="outcomes" data-title="Чем заканчиваются прогоны, за 30 дней" data-key="Конец" data-value="Прогоны" data-share="Доля" data-answered="Ответ" data-failed="Сбой" data-stopped="Остановлен пользователем" data-limit="Предел шагов или токенов"></figure>
<figure class="usage-chart" data-chart="failures" data-title="15 самых частых видов сбоев за 30 дней" data-key="Вид" data-value="Сбои" data-installs="Установки"></figure>
<figure class="usage-chart" data-chart="families" data-title="Сбои прогонов по сервисам моделей за 30 дней" data-key="Сервис" data-installs="Установки" data-runs="Прогоны" data-failed="Сбои" data-rate="Доля сбоев" data-format="{0} ({1} из {2})"></figure>
<figure class="usage-chart" data-chart="tool_errors" data-title="15 инструментов с наибольшим числом ошибок и доля ошибок за 30 дней" data-key="Инструмент" data-value="Ошибки" data-calls="Вызовы" data-rate="Доля ошибок"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="steps" data-title="Шаги за прогон" data-key="Шаги" data-value="Прогоны" data-share="Доля" data-s0="Нет" data-s1="1" data-s2_3="2–3" data-s4_7="4–7" data-s8_15="8–15" data-s16_plus="16+"></figure>
<figure class="usage-chart" data-chart="durations" data-title="Активное время прогона" data-key="Время" data-value="Прогоны" data-share="Доля" data-t0_10="До 10 с" data-t10_30="10–30 с" data-t30_60="30–60 с" data-t60_180="1–3 мин" data-t180_plus="Больше 3 мин"></figure>
<figure class="usage-chart" data-chart="tokens" data-title="Токены за прогон" data-key="Токены" data-value="Прогоны" data-share="Доля" data-k0_5="До 5 тыс." data-k5_20="5–20 тыс." data-k20_50="20–50 тыс." data-k50_200="50–200 тыс." data-k200_plus="Больше 200 тыс."></figure>
</div>
<figure class="usage-chart" data-chart="plans" data-title="Планы за 30 дней" data-key="Итог" data-value="Планы" data-shown="Показаны" data-applied="Применены" data-cancelled="Отменены" data-undone="Откачены" data-auto="Применены в режиме «Авто»"></figure>
</div>

### Окружение

<div class="usage-section">
<figure class="usage-chart" data-chart="plugin" data-title="Версии плагина, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="Версии QGIS, установки за 30 дней" data-key="Версия" data-value="Установки"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="os" data-title="Операционные системы" data-key="Система" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="provider" data-title="Серверы моделей" data-key="Сервер" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="dialect" data-title="Диалекты API" data-key="Диалект" data-value="Установки"></figure>
</div>
<figure class="usage-chart" data-chart="family" data-title="Сервисы моделей, установки за 30 дней" data-key="Сервис" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="locale" data-title="Языки интерфейса, установки за 30 дней" data-key="Язык" data-value="Установки"></figure>
<figure class="usage-chart" data-chart="tools" data-title="15 самых вызываемых инструментов за 30 дней" data-key="Инструмент" data-value="Вызовы"></figure>
<figure class="usage-chart" data-chart="skills" data-title="15 самых загружаемых навыков за 30 дней" data-key="Навык" data-value="Загрузки"></figure>
</div>

Операционные системы, серверы моделей и диалекты API считают установки за
последние 30 дней, диапазоны по прогонам и диалогам охватывают те же дни.
Установка, обновившаяся за месяц, попадает под обе версии.

Недели начинаются с понедельника; вернувшаяся установка была активна и в одну
из прошлых недель. График активации отсчитывает каждый шаг от первого дня
установки; в «Пока нет» попадают и установки, которые слишком новые, чтобы
дойти до шага. Прогон — это один запрос, повтор или проверка после применения.
Активное время считает работу модели и инструментов, а не ожидание вашего
ответа; запросы до применения считаются от предыдущего применения в диалоге.

Плагин 0.4.0 не сообщает о настройке модели и об ошибках вызовов, поэтому
воронка считает его установки, запускавшие агента, настроенными, а доля ошибок
не учитывает его вызовы. Скачивания включают обновления.
