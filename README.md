# Практическая работа №2 — конфигурационное управление

Вариант №11. Проект реализует этапы 1–5: YAML-конфигурацию, ручное
получение NuGet-зависимостей, рекурсивный BFS-граф, обратный поиск,
Mermaid-представление, SVG-диаграммы и ASCII-дерево.

## Настройки

Основной конфиг: `config/config.yaml`. Путь можно переопределить через
`--config`.

| Ключ | Назначение |
| --- | --- |
| `package_name` | корневой пакет или узел графа |
| `repository` | NuGet V3 index URL или путь к тестовому JSON-графу |
| `test_mode` | переключение между NuGet и локальным графом |
| `version` | версия корневого NuGet-пакета |
| `output_file` | путь к SVG-файлу, расширение `.svg` обязательно |
| `ascii_tree` | выводить ли дерево в терминал |
| `max_depth` | максимальная глубина обхода |
| `filter` | подстрока имени исключаемого пакета |

Все строки, типы и обязательные ключи конфигурации проверяются при запуске.

## Получение зависимостей NuGet

Программа запрашивает индекс NuGet V3 стандартным HTTP-клиентом Python,
скачивает `.nupkg`, открывает ZIP и вручную читает `.nuspec` через
`xml.etree.ElementTree`. Так для каждого узла извлекаются прямые зависимости;
транзитивный граф строится собственным обходом. Менеджеры пакетов,
resolver'ы, NuGet SDK и GitHub для получения зависимостей не используются.

Для простых version range выбирается включённая граница. Например,
`[2.4.0, 3.0.0)` даёт `2.4.0`, а `(2.4.0, 3.0.0]` даёт `3.0.0`.
Если диапазон открыт или обе границы исключены, программа сообщает об
ошибке. Это не полноценный NuGet resolver: доступность версии и целевые
платформы не проверяются.

## Этапы 3–4: обход графа

Граф строится рекурсивной обработкой очереди FIFO (BFS). Обход учитывает
`max_depth`, пропускает имена с `filter`, сохраняет рёбра циклов и не
раскрывает узел повторно. Тестовый файл `config/test_graph.json` содержит
ветвление, общие зависимости, цикл и листья; имена — большие латинские буквы.

Обратные зависимости запускаются параметром
`--reverse-dependencies PACKAGE`. Сначала строится граф от `package_name`,
затем тот же BFS проходит инвертированные рёбра. Результат включает прямых
и транзитивных зависимых и ограничивается `max_depth`/`filter`. Целевой
пакет должен входить в граф от корня.

```sh
./run.sh --config config/test_mode.yaml --reverse-dependencies G
```

## Этап 5: Mermaid, SVG и ASCII-дерево

Обычный запуск печатает рёбра и, если `ascii_tree: true`, ASCII-дерево.
Дерево помечает циклы и повторные узлы. Программа сохраняет Mermaid-исходник
рядом с SVG: для `dependencies.svg` создаются `dependencies.mmd` и
`dependencies.svg`. SVG рендерится локальным кодом из того же графа; сетевой
Mermaid-сервис и дополнительные runtime-пакеты не нужны.

`--package` задаёт корень для демонстрации другого пакета,
`--output` переопределяет путь SVG. Три тестовых примера сохранены в
`examples/visualizations/`:

```sh
./run.sh --config config/test_mode.yaml --package A \
  --output examples/visualizations/package_a.svg
./run.sh --config config/test_mode.yaml --package C \
  --output examples/visualizations/package_c.svg
./run.sh --config config/test_mode.yaml --package G \
  --output examples/visualizations/package_g.svg
```

Примеры: [A SVG](examples/visualizations/package_a.svg) ·
[C SVG](examples/visualizations/package_c.svg) ·
[G SVG](examples/visualizations/package_g.svg). Для каждого SVG сохранён
Mermaid-исходник `.mmd` с тем же базовым именем.

### Сравнение с NuGet UI

В Visual Studio пакеты проекта видны в NuGet Package Manager и в узле
Solution Explorer `Dependencies > Packages` ([документация Microsoft](https://learn.microsoft.com/en-us/nuget/tools/package-manager-ui)).
Штатное представление ориентировано на установленные проектные пакеты;
эта программа показывает направленные связи одного корневого `.nuspec` и
делает Mermaid/SVG. Общие зависимости в SVG сведены в один узел, а проектный
NuGet-граф может учитывать target framework, конфликтующие требования и
результат restore. Поэтому состав и версии могут расходиться с графом из
`.nuspec`, где используется упрощённый выбор версии ([правила разрешения NuGet](https://learn.microsoft.com/en-us/nuget/concepts/dependency-resolution)).

Сравнение описывает различия представлений и правил. Команды NuGet/.NET для
получения списка зависимостей не запускались: методичка запрещает применять
готовые менеджеры и resolver'ы для этой задачи.

## Запуск и тесты

Требуются Python 3.10+ и PyYAML.

```sh
./run.sh --config config/config.yaml
./run.sh --config config/test_mode.yaml
python3 -m unittest discover -s tests -v
```

Тесты используют локальные данные и моки, сети не требуют.
