# Установка

Плагину нужен **QGIS 4.0 или новее**. На QGIS 3.x он не работает.

## 1. Установка

Установите **AI Agent** через **Модули → Управление модулями**.

Чтобы поставить конкретную версию, скачайте `ai_agent-<версия>.zip` из
[релизов на GitHub](https://github.com/mzarov/qgis-ai-agent/releases/latest) и
выберите **Установить из ZIP** в том же окне. Не берите архивы GitHub «Source
code» и «Download ZIP»: имя папки в них не годится как имя плагина.

Чтобы собрать архив из рабочей копии, выполните
`python3 tools/build_plugin.py`. Он кладёт `dist/ai_agent-<версия>.zip`.

Плагину не нужны Python-зависимости, кроме самого QGIS.

## 2. Подключение модели

Откройте панель и нажмите кнопку настроек. На странице **Подключение**
выберите плитку провайдера или введите свой адрес:

- **Адрес сервера**: базовый URL, без `/chat/completions`.
- **Модель**: имя модели у вашего провайдера.
- **Ключ API**: хранится зашифрованным в базе учётных данных QGIS, а не в
  файле настроек. Когда вы впервые сохраняете ключ, QGIS спрашивает мастер-пароль.

**Проверить подключение** отправляет один короткий запрос и показывает ответ.
Заодно проверяется, видит ли модель картинки; если нет, агент проверяет свою
работу чтением данных, а не по отрисованной карте. Проверьте снова после смены
модели.

Формат API (`auto`, `openai` или `anthropic`) и тип авторизации находятся на
странице **Дополнительно**. `auto` выбирает формат по адресу.

Модель должна поддерживать вызов функций. Если эндпоинт его не умеет, плагин
сам переходит на текстовый протокол JSON. Лучше всего работают модели от
примерно 30B параметров; маленькие модели на 7–8B часто ошибаются в вызовах
инструментов.

### Провайдеры

| Провайдер | Адрес сервера |
| --- | --- |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Anthropic | `https://api.anthropic.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Mistral | `https://api.mistral.ai/v1` |

Любой другой OpenAI-совместимый сервис работает со своим адресом.

### Локальные модели

Адресу на `localhost` ключ не нужен.

| Сервер | Адрес сервера |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp server | `http://localhost:8080/v1` |

Локальный сервер оставляет запросы на компьютере, только если так настроен;
проверьте, не записывает ли он их и не пересылает ли дальше.

### Геокодирование

По умолчанию геокодирование выключено. На странице **Геокодирование**
выберите демо-сервис Photon для редких запросов или свой сервер Nominatim.
Каждый запрос сначала спрашивает подтверждение.

Прежде чем подключать удалённого провайдера, прочитайте
[«Данные и конфиденциальность»](privacy.md).

## 3. Установка для разработки

Вместо пересборки ZIP сделайте ссылку на папку пакета в профиле QGIS. Профиль
открывается через **Настройки → Профили пользователя → Открыть папку
активного профиля**; плагины лежат в `python/plugins`.

```bash
PLUGINS_DIR="$HOME/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins"
mkdir -p "$PLUGINS_DIR"
ln -sfn "$(pwd)/ai_agent" "$PLUGINS_DIR/ai_agent"
```

Ссылайтесь на `ai_agent/`, а не на корень репозитория. Перезагружайте плагин
через **Plugin Reloader**. После добавления или переноса модулей
перезапустите QGIS.

## 4. Тесты

```bash
python3 -m unittest discover -s tests -t .
poetry install
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

Модульные тесты идут на обычном Python с заменителями QGIS из
`tests/stub.py`. Покрытие ветвей:
`poetry run coverage run -m unittest discover -s tests -t .` и
`poetry run coverage html`.

Наборам в настоящем QGIS нужен Python из QGIS. На macOS:

```bash
R=/Applications/QGIS-final-4_2_1.app/Contents
cd tests && QT_QPA_PLATFORM=offscreen PYTHONHOME=$R/Resources \
  PYTHONPATH=$R/Resources/python3.12:$R/Resources/python3.12/lib-dynload:$R/Resources/python3.12/site-packages \
  $R/MacOS/python3.12 real_qgis_workflows.py
```

Остальные наборы и ручные проверки описаны в
[смоук-чеклисте](smoke_checklist.md).

Логотипы провайдеров взяты из [Simple Icons](https://simpleicons.org) (CC0) и
остаются товарными знаками владельцев; значки интерфейса —
[Lucide](https://lucide.dev) (ISC).
