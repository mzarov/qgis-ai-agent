# Установка QGIS 4 и подключение плагина (macOS)

## 1. Установка QGIS 4

1. Скачайте установщик для macOS: [qgis.org/download](https://qgis.org/download) или [qgis.org/downloads/macOS](https://qgis.org/downloads/macOS/) — выберите **QGIS 4** (или актуальный LTR/nightly для 4.x).
2. Откройте скачанный `.dmg` и перетащите QGIS в папку **Applications**.
3. Запустите QGIS из Applications. При первом запуске может потребоваться разрешение в **Системные настройки → Конфиденциальность и безопасность**.

## 2. Путь к плагинам

Каталог плагинов лежит в профиле пользователя. На macOS обычно:

- **QGIS 4:** `~/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins`
- **QGIS 3:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`

Точный путь можно посмотреть в QGIS: **Настройки → Профили пользователя → Открыть папку активного профиля**, затем зайти в `python/plugins`.

Если папки `python/plugins` ещё нет — создайте её (или запустите QGIS один раз и установите любой плагин из репозитория, тогда папка создастся сама).

## 3. Символическая ссылка на плагин

Чтобы не копировать плагин при изменениях, сделайте симлинк из репозитория в каталог плагинов.

В терминале:

```bash
# Каталог плагинов QGIS 4 (подставьте свой путь, если профиль не default)
PLUGINS_DIR="$HOME/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins"

# Создать папку, если её нет
mkdir -p "$PLUGINS_DIR"

# Путь к репозиторию плагина (замените на свой)
PLUGIN_SRC="/Users/mzarov/Documents/projects/qgis_ai_agent"

# Симлинк: в plugins будет папка qgis_ai_agent → твой репозиторий
ln -sfn "$PLUGIN_SRC" "$PLUGINS_DIR/qgis_ai_agent"
```

Проверка:

```bash
ls -la "$PLUGINS_DIR/qgis_ai_agent"
# Должно быть: ... qgis_ai_agent -> /Users/mzarov/Documents/projects/qgis_ai_agent
```

Важно: в `$PLUGINS_DIR` должна быть именно папка **qgis_ai_agent** (имя репозитория/плагина), указывающая на корень проекта, где лежат `__init__.py`, `metadata.txt`, `src/`.

## 4. Подключение плагина в QGIS

1. Запустите QGIS 4.
2. Меню **Плагины → Управление и установка плагинов**.
3. Вкладка **Установлено** — найдите **QGIS AI Agent** и включите галочку. Если плагина нет, нажмите **Обновить** или перезапустите QGIS.
4. После включения в меню появится пункт **QGIS AI Agent**; можно вынести его на панель инструментов.

При изменении кода перезагрузите плагин. Если менялась структура пакетов, нужен **полный перезапуск QGIS**: снятие галочки не выгружает подмодули из `sys.modules`. Для обычных правок удобен плагин **Plugin Reloader** (`Ctrl+F5`).

Консоль Python держит собственный кэш модулей. Чтобы сбросить его без перезапуска:

```python
import sys; [sys.modules.pop(n) for n in list(sys.modules) if n.startswith("qgis_ai_agent")]
```

## 5. Зависимости Python (requests, keyring)

Функции «Настройки» и запросы к ИИ требуют библиотек `requests` и `keyring`. **Плагин загружается и без них**, но при первом сохранении ключа или запросе к модели появится сообщение с инструкцией по установке.

Установить зависимости нужно **в тот Python, с которым запускается QGIS** (часто это встроенный Python внутри приложения).

### macOS (QGIS из .app)

Точный путь к Python в каждом сборке QGIS может отличаться. **Важно:** нужен путь к интерпретатору **Python** (например, `.../bin/python3`), а не к приложению QGIS (`QGIS-final-4_0_0` или `QGIS`) — с последним команда `-m pip` не сработает.

**Надёжный способ:**

1. Запустите QGIS.
2. Меню **Плагины → Консоль Python** (включите консоль, если она скрыта).
3. В консоли выполните:

   ```python
   import sys; print(sys.executable)
   ```

4. Скопируйте выведенный путь (часто `…/Frameworks/Python.framework/Versions/3.12/bin/python3` внутри `.app`).
5. **Закройте QGIS** (на время установки пакетов).
6. В терминале выполните (подставьте скопированный путь; кавычки обязательны при пробелах):

   ```bash
   "/СКОПИРОВАННЫЙ_ПУТЬ" -m pip install requests keyring
   ```

   Примеры (подставьте имя своего приложения):

   ```bash
   # Вариант 1 — Python в MacOS (часто в сборках Kyngchaos и др.)
   /Applications/QGIS-final-4_0_0.app/Contents/MacOS/python -m pip install requests keyring
   # Вариант 2 — Python во Frameworks
   /Applications/QGIS-final-4_0_0.app/Contents/Frameworks/Python.framework/Versions/3.12/bin/python3 -m pip install requests keyring
   ```

7. Запустите QGIS снова и перезагрузите плагин.

**Вариант через поиск в .app** (если консоль недоступна):

```bash
# Подставьте имя вашего приложения QGIS (например QGIS.app или QGIS-final-4_0_0.app)
APP="/Applications/QGIS-final-4_0_0.app"
PY=$(find "$APP" -name "python*" -type f 2>/dev/null | head -1)
if [ -n "$PY" ]; then "$PY" -m pip install requests keyring; else echo "Python не найден в $APP"; fi
```

### Windows / Linux

В QGIS откройте **Плагины → Консоль Python**, выполните `import sys; print(sys.executable)` и используйте этот путь:

```bash
"путь\к\python.exe" -m pip install requests keyring
```

После установки перезагрузите плагин (снять и снова включить в менеджере плагинов).
