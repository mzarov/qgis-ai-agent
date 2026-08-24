# Layout Tooling Smoke Checklist

Чеклист smoke-валидации качества макетирования после апгрейда зон/границ/anti-overlap.

## Покрытые сценарии

- `A4 portrait` (210x297): `create_layout -> add_map -> add_legend -> add_label(role=title, alignment=center) -> add_scale_bar`
- `A4 landscape` (297x210): тот же поток.
- `A3 landscape` (420x297): тот же поток.

## Результаты smoke-проверки

- `title/top-center` - PASS: для `role=title` принудительно применяется top-center и фиксированная верхняя зона.
- `text-stability` - PASS: `add_label` нормализует невидимые символы (`Cf/Cc`, ZWSP/BOM, NBSP), геометрия стабильна.
- `bounds` - PASS: применяется `clamp_to_page_bounds` до/после размещения, выход за границы страницы предотвращён.
- `anti-overlap` - PASS: единый pipeline `place_item_with_policy` используется для map/legend/label/scalebar.
- `scalebar-readability` - PASS: безопасная адаптация `segment_count` и `units_per_segment` при переполнении.
- `scalebar-overlap` - PASS: для линейки включён поиск с `include_maps=True`, размещение в footer-зоне с финальным post-clamp.

## Антирегрессия (контрольный список)

- `existing-layout-reuse`: follow-up шаги применяются к существующему `layout_name` без принудительного `create_layout`.
- `missing-map-error`: `add_scale_bar` возвращает понятную ошибку при отсутствии карты.
- `planning-center-semantics`: `center` для заголовка трактуется как `top-center`.
- `planning-bounds-rule`: планировщик не должен предлагать элементы вне страницы; при out-of-bounds координатах инструменты делают safe-clamp.
- `planning-role-guidance`: для текста приоритет `title/subtitle/footer`, а не «плавающий» generic label.

## Техническая проверка после правок

- Выполнена компиляция Python-модулей (`python3 -m compileall ...`) для изменённых файлов: PASS.
