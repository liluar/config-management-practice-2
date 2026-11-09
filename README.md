# Практическая работа №2 — конфигурационное управление

Вариант №11. Проект на Python читает YAML-конфигурацию, вручную получает
прямые зависимости NuGet из `.nuspec`, строит рекурсивный обход в ширину (BFS),
ищет обратные зависимости и сохраняет граф в Mermaid и SVG. ASCII-дерево
выводится по настройке `ascii_tree`.

## Требования и ограничения

Нужны Python 3.10+ и PyYAML (`python3 -m pip install PyYAML`). Программа
обращается к NuGet V3 через стандартные HTTP-инструменты Python, скачивает
`.nupkg`, распаковывает ZIP и читает `.nuspec` через `xml.etree.ElementTree`.
NuGet CLI/SDK, `dotnet`, GitHub и готовые средства разрешения графа
зависимостей не используются для получения списка зависимостей.

Выбор версии намеренно упрощён: для точной версии берётся она сама, для
диапазона — включённая нижняя граница, иначе включённая верхняя. Открытые
диапазоны и диапазоны без включённой конкретной границы завершаются ошибкой.
Это не полноценное разрешение NuGet version ranges: код не проверяет
совместимость с target framework, наличие выбранной версии и конфликты версий.
Кроме того, зависимости из разных групп `.nuspec` объединяются; они могут
отличаться от группы, выбранной для конкретного проекта.

## Конфигурация и аргументы

По умолчанию используется `config/config.yaml`; путь можно заменить через
`--config PATH`. Все восемь YAML-ключей обязательны:

| Ключ | Назначение |
| --- | --- |
| `package_name` | ID корневого NuGet-пакета или тестового узла |
| `repository` | URL индекса NuGet V3; в test mode — путь к JSON-графу |
| `test_mode` | `true` читает локальный граф, `false` использует NuGet V3 |
| `version` | версия корневого пакета; в test mode зависимости получают `1.0.0` |
| `output_file` | путь для SVG; рядом сохраняется Mermaid `.mmd` |
| `ascii_tree` | выводить ASCII-дерево (`true`/`false`) |
| `max_depth` | максимальная глубина BFS; корень имеет глубину 0 |
| `filter` | исключать зависимость, если имя содержит эту подстроку без учёта регистра |

Поддерживаемые CLI-параметры:

| Параметр | Назначение |
| --- | --- |
| `--config PATH` | выбрать YAML-файл |
| `--package ID` | заменить корневой пакет из YAML |
| `--output PATH` | заменить путь к SVG (Mermaid сохраняется рядом) |
| `--reverse-dependencies PACKAGE` | вывести обратные рёбра для пакета, найденного в построенном графе |

Параметры версии, режима, глубины и фильтра задаются в YAML. Программа
проверяет наличие ключей и типы значений до построения графа.

## Устройство программы

### `src/main.py`

- `GraphState` хранит граф, множество посещённых пакетов и FIFO-очередь BFS.
  `DEFAULT_CONFIG`, `REQUIRED_KEYS`, `STRING_KEYS`, `MIN_DEPTH`,
  `TEST_VERSION` и `CAPITAL_PACKAGE` задают значения по умолчанию и правила
  проверки; `DependencyProvider` описывает тип функции поставщика зависимостей.
- `parse_arguments` объявляет CLI-параметры; `read_yaml` загружает YAML через
  `yaml.safe_load`; `require_mapping` проверяет корневой тип конфигурации.
- `validate_required_keys`, `validate_string_fields`,
  `validate_boolean_fields` и `validate_depth` проверяют обязательные поля,
  строки, логические значения и неотрицательную глубину.
- `validate_config` запускает проверки конфигурации, а `load_config` читает и
  возвращает проверенные настройки.
- `read_test_graph` проверяет JSON-граф и имена узлов заглавными латинскими
  буквами; `test_provider` создаёт поставщик соседей для test mode.
- `expand_package` добавляет подходящие рёбра и новые узлы очереди.
  `build_dependency_graph` рекурсивно обрабатывает FIFO-очередь и соблюдает
  глубину, фильтр и множество посещённых узлов.
- `configured_provider` выбирает локальный JSON или NuGet-загрузчик.
  `print_graph` печатает рёбра; `main` связывает конфигурацию, обход, вывод и
  обработку ошибок.
- `reverse_provider` инвертирует рёбра для обратного обхода;
  `build_reverse_dependency_graph` находит прямых и транзитивных зависимых,
  а `print_reverse_graph` показывает результат.
- Вложенная функция `provide` в `test_provider` возвращает зависимости
  локального узла. Вложенная `visit_queue` в `build_dependency_graph`
  рекурсивно обрабатывает узлы в порядке BFS.

### `src/nuget.py`

- `HTTP_TIMEOUT`, `NUPKG_SUFFIX`, `NUSPEC_SUFFIX`, `PACKAGE_BASE_TYPE`,
  `VERSION_PART` и `VERSION_RANGE` задают таймаут, формат пакета и правила
  распознавания ресурсов и спецификаций версий.
- `download_bytes` скачивает ответ NuGet V3; `resource_types` нормализует
  поле типов ресурса; `package_base_address` находит адрес хранилища пакетов.
- `package_url` формирует URL `.nupkg`; `local_name` убирает XML namespace;
  `dependency_entries` извлекает ID и version spec из элементов и групп.
- `parse_nuspec` разбирает прямые зависимости XML; `nuspec_contents` открывает
  `.nupkg` как ZIP и возвращает содержимое `.nuspec`.
- `exact_version` распознаёт точную версию в квадратных скобках;
  `ranged_version` выбирает включённую границу; `select_version` применяет
  упрощённую стратегию к версии или диапазону.
- `get_direct_dependencies` скачивает пакет и читает его `.nuspec`;
  `get_transitive_dependencies` выбирает конкретные версии для следующего
  уровня обхода.

### `src/visualization.py`

- `mermaid_source` формирует Mermaid-текст со стабильными ID;
  `node_levels` назначает минимальные уровни узлам обходом в ширину.
- `node_width` оценивает ширину SVG-узла; `layout_nodes` размещает узлы
  по колонкам уровней; `edge_svg` формирует SVG-путь ребра со стрелкой.
- `svg_source` создаёт автономное SVG с узлами и рёбрами;
  `write_visualization` сохраняет Mermaid и SVG рядом.
- `ascii_tree` строит дерево и отмечает циклы/повторные узлы;
  `print_ascii_tree` печатает это дерево.
- `MERMAID_HEADER` и `SVG_MARGIN`, `SVG_NODE_HEIGHT`, `SVG_MIN_NODE_WIDTH`,
  `SVG_CHAR_WIDTH`, `SVG_HORIZONTAL_PADDING`, `SVG_HORIZONTAL_GAP`,
  `SVG_VERTICAL_GAP`, `SVG_FONT_SIZE`, `SVG_CURVE_OFFSET` и
  `SVG_CYCLE_OFFSET` задают формат диаграммы и геометрию SVG.

## Запуск, сборка и тесты

Отдельная компиляция не нужна. Из корня репозитория:

```sh
./run.sh --config config/config.yaml
./run.sh --config config/test_mode.yaml
./run.sh --config config/test_mode.yaml --package C
./run.sh --config config/test_mode.yaml --reverse-dependencies G
python3 -m unittest discover -s tests -v
```

Сетевой режим указан в `config/config.yaml`; тестовый граф и пример настроек
находятся в `config/`. Тесты используют локальные данные и моки, сеть им не
нужна. Каждый обычный запуск выводит граф, сохраняет `.mmd` и `.svg`, а при
`ascii_tree: true` также печатает ASCII-дерево.

## Этап 5: реальные NuGet-примеры

В `examples/visualizations/real/` сохранены Mermaid и SVG, созданные запуском
программы с теми же NuGet V3 → `.nupkg` → ZIP → `.nuspec` и собственным BFS.
Для воспроизводимости все три примера ограничены `max_depth: 2`; графы
объединяют зависимости, объявленные в группах `.nuspec`. Каждый SVG имеет
одноимённый `.mmd`:

| NuGet-пакет | Фиксированная версия | Пример |
| --- | --- | --- |
| `Newtonsoft.Json` | `13.0.3` | [Mermaid](examples/visualizations/real/newtonsoft_json_13_0_3.mmd), [SVG](examples/visualizations/real/newtonsoft_json_13_0_3.svg) |
| `Polly` | `8.5.2` | [Mermaid](examples/visualizations/real/polly_8_5_2.mmd), [SVG](examples/visualizations/real/polly_8_5_2.svg) |
| `FluentValidation` | `11.11.0` | [Mermaid](examples/visualizations/real/fluentvalidation_11_11_0.mmd), [SVG](examples/visualizations/real/fluentvalidation_11_11_0.svg) |

Команды повторного создания примеров (при наличии сетевого доступа к NuGet):

```sh
./run.sh --config config/config.yaml --package Newtonsoft.Json \
  --output examples/visualizations/real/newtonsoft_json_13_0_3.svg
./run.sh --config config/config.yaml --package Polly \
  --output examples/visualizations/real/polly_8_5_2.svg
./run.sh --config config/config.yaml --package FluentValidation \
  --output examples/visualizations/real/fluentvalidation_11_11_0.svg
```

В `config/config.yaml` перед каждым запуском выставьте `version` в значение
из таблицы и `max_depth: 2`. Фиксированная версия корня задаётся конфигурацией;
CLI переопределяет имя и выходной путь.

## Сопоставление с NuGet

Прямые метаданные также сверены с официальными страницами NuGet:
[Newtonsoft.Json 13.0.3](https://www.nuget.org/packages/Newtonsoft.Json/13.0.3),
[Polly 8.5.2](https://www.nuget.org/packages/Polly/8.5.2) и
[FluentValidation 11.11.0](https://www.nuget.org/packages/FluentValidation/11.11.0).
ID пакетов совпадают с данными загруженных `.nuspec`. Например, страница Polly
показывает `Polly.Core (>= 8.5.2)` для каждой target framework-группы, а для
FluentValidation указывает `System.Threading.Tasks.Extensions (>= 4.5.4)` в
группе .NET Standard 2.0; у остальных включённых групп зависимостей нет.
Newtonsoft.Json не имеет зависимостей для .NET Framework 2.0–4.5 и .NET
Standard 2.0, но объявляет их в группах .NET Standard 1.0/1.3. Поэтому пример
показывает объединение метаданных разных framework-групп, а не одну группу,
выбранную restore для проекта.

NuGet Package Manager UI показывает пакеты проекта и их разрешённые версии,
а restore выбирает совместимые зависимости с учётом target framework и
конфликтов версий. Поэтому полный проектный граф может отличаться от
объединённого учебного графа. Команды NuGet/dotnet для вычисления списка
зависимостей или графа при выполнении этой работы не используются.
