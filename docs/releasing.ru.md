# Выпуск версии

Выпуск — это один ручной запуск `.github/workflows/release.yml`. Он
прогоняет тесты, собирает ZIP, загружает его на
[plugins.qgis.org](https://plugins.qgis.org/plugins/ai_agent/) и только после
этого ставит тег и публикует GitHub-релиз с приложенным ZIP.

## Однократная настройка

1. На plugins.qgis.org откройте **AI Agent → Tokens**
   (`https://plugins.qgis.org/plugins/ai_agent/tokens/`) и создайте токен.
2. В GitHub откройте **Settings → Secrets and variables → Actions** и
   сохраните его как секрет `QGIS_PLUGIN_TOKEN`.

## Каждый выпуск

1. Поднимите `version=` в `ai_agent/metadata.txt` и `version` в
   `pyproject.toml`. Добавьте запись в начало `changelog=`: версия отдельной
   строкой, затем до пяти коротких пунктов с `- `. Каждая строка changelog
   должна быть с отступом: строка без отступа ломает метаданные.
2. Смержите в `main`.
3. Запустите **Actions → release → Run workflow** на `main`.

До сборки запуск ставит ZIP в QGIS в контейнере и прогоняет рабочие сценарии
в настоящем QGIS и сквозные сценарии (см. [смоук-чеклист](smoke_checklist.md)).
С галочкой **live_model_check** он ещё гоняет сценарии с настоящей моделью и
тратит токены провайдера.

Запуск останавливается до публикации, если упал тест, тег этой версии уже
существует или в changelog нет записи для неё. Если plugins.qgis.org отклонил
загрузку, тег не ставится. `python3 tools/release_notes.py` печатает текст
релиза.

Новая версия появляется на plugins.qgis.org после автоматических проверок и,
для аккаунтов без роли одобряющего, ручного одобрения.
