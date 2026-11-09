"""Конфигурация и рекурсивный обход графа зависимостей."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from nuget import get_transitive_dependencies
from visualization import print_ascii_tree, write_visualization

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
REQUIRED_KEYS = ("package_name", "repository", "test_mode", "version",
                 "output_file", "ascii_tree", "max_depth", "filter")
STRING_KEYS = ("package_name", "repository", "version", "output_file")
MIN_DEPTH = 0
TEST_VERSION = "1.0.0"
CAPITAL_PACKAGE = re.compile(r"^[A-Z]+$")
DependencyProvider = Callable[[str, str], list[tuple[str, str]]]


@dataclass
class GraphState:
    """Хранить состояние очереди и посещённых узлов BFS."""

    graph: dict[str, list[str]]
    visited: set[str]
    queue: deque[tuple[str, str, int]]


def parse_arguments() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Граф зависимостей")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--reverse-dependencies", metavar="PACKAGE",
        help="показать пакеты, зависящие от PACKAGE",
    )
    parser.add_argument("--package", help="переопределить корневой пакет")
    parser.add_argument("--output", type=Path, help="путь к SVG-файлу")
    return parser.parse_args()


def read_yaml(path: Path) -> Any:
    """Прочитать YAML-файл."""
    try:
        with path.open("r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file)
    except FileNotFoundError as error:
        raise ValueError(f"Файл конфигурации не найден: {path}") from error
    except yaml.YAMLError as error:
        raise ValueError(f"Некорректный YAML в файле: {path}") from error
    except OSError as error:
        raise ValueError(f"Не удалось прочитать файл: {path}") from error


def require_mapping(data: Any) -> dict[str, Any]:
    """Проверить тип корневого значения конфигурации."""
    if not isinstance(data, dict):
        raise ValueError("Конфигурация должна быть YAML-отображением")
    return data


def validate_required_keys(config: dict[str, Any]) -> None:
    """Проверить наличие обязательных полей."""
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError("Отсутствуют параметры: " + ", ".join(missing))


def validate_string_fields(config: dict[str, Any]) -> None:
    """Проверить строковые поля и фильтр."""
    for key in STRING_KEYS:
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"Параметр '{key}' должен быть непустой строкой")
    if not isinstance(config["filter"], str):
        raise ValueError("Параметр 'filter' должен быть строкой")


def validate_boolean_fields(config: dict[str, Any]) -> None:
    """Проверить логические параметры конфигурации."""
    for key in ("test_mode", "ascii_tree"):
        if not isinstance(config[key], bool):
            raise ValueError(f"Параметр '{key}' должен быть true или false")


def validate_depth(config: dict[str, Any]) -> None:
    """Проверить неотрицательную целочисленную глубину."""
    depth = config["max_depth"]
    if type(depth) is not int or depth < MIN_DEPTH:
        raise ValueError("Параметр 'max_depth' должен быть целым >= 0")


def validate_config(data: Any) -> dict[str, Any]:
    """Проверить обязательные поля и их типы."""
    config = require_mapping(data)
    validate_required_keys(config)
    validate_string_fields(config)
    validate_boolean_fields(config)
    validate_depth(config)
    return config


def load_config(path: Path) -> dict[str, Any]:
    """Загрузить конфигурацию и проверить значения."""
    return validate_config(read_yaml(path))


def read_test_graph(path: Path) -> dict[str, list[str]]:
    """Прочитать тестовый граф с именами пакетов A-Z."""
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        message = f"Не удалось прочитать тестовый граф: {path}"
        raise ValueError(message) from error
    if not isinstance(graph, dict):
        raise ValueError("Тестовый граф должен быть JSON-объектом")
    for package, dependencies in graph.items():
        if not CAPITAL_PACKAGE.fullmatch(package):
            raise ValueError(f"Недопустимое имя пакета: {package}")
        if not isinstance(dependencies, list):
            raise ValueError(f"Зависимости {package} должны быть списком")
        for dependency in dependencies:
            if (not isinstance(dependency, str)
                    or not CAPITAL_PACKAGE.fullmatch(dependency)):
                raise ValueError(f"Недопустимая зависимость пакета {package}")
    return graph


def test_provider(graph: dict[str, list[str]]) -> DependencyProvider:
    """Создать поставщик прямых зависимостей для тестового графа."""
    def provide(package: str, version: str) -> list[tuple[str, str]]:
        """Вернуть смежные узлы локального графа."""
        del version
        return [(name, TEST_VERSION) for name in graph.get(package, [])]
    return provide


def expand_package(
    package: str, version: str, depth: int, filter_text: str,
    provider: DependencyProvider, state: GraphState,
) -> None:
    """Добавить рёбра узла и поставить новые узлы в FIFO-очередь."""
    for dependency, required_version in provider(package, version):
        if filter_text and filter_text.casefold() in dependency.casefold():
            continue
        state.graph[package].append(dependency)
        state.graph.setdefault(dependency, [])
        if dependency not in state.visited:
            state.visited.add(dependency)
            state.queue.append((dependency, required_version, depth + 1))


def build_dependency_graph(
    root: str, version: str, max_depth: int, filter_text: str,
    provider: DependencyProvider,
) -> dict[str, list[str]]:
    """Построить граф BFS с рекурсивной обработкой очереди."""
    graph = {root: []}
    visited = {root}
    queue = deque([(root, version, 0)])
    state = GraphState(graph, visited, queue)

    def visit_queue() -> None:
        """Рекурсивно обработать очередь в порядке BFS."""
        if not state.queue:
            return
        package, package_version, depth = state.queue.popleft()
        if depth < max_depth:
            expand_package(package, package_version, depth, filter_text,
                           provider, state)
        visit_queue()

    visit_queue()
    return state.graph


def configured_provider(
    config: dict[str, Any], config_path: Path
) -> DependencyProvider:
    """Выбрать поставщика NuGet или локального тестового графа."""
    if not config["test_mode"]:
        return lambda package, version: get_transitive_dependencies(
            package, version, config["repository"])
    graph_path = Path(config["repository"])
    if not graph_path.is_absolute():
        graph_path = config_path.resolve().parent / graph_path
    return test_provider(read_test_graph(graph_path))


def print_graph(root: str, version: str, graph: dict[str, list[str]]) -> None:
    """Напечатать построенные рёбра графа."""
    print(f"Граф зависимостей пакета {root} {version}:")
    edges = [(source, target) for source, targets in graph.items()
             for target in targets]
    if not edges:
        print("Зависимостей нет.")
        return
    for source, target in edges:
        print(f"{source} -> {target}")


def reverse_provider(
    graph: dict[str, list[str]],
) -> DependencyProvider:
    """Создать поставщик смежных пакетов обратного графа."""
    reversed_graph = {package: [] for package in graph}
    for package, dependencies in graph.items():
        for dependency in dependencies:
            reversed_graph.setdefault(dependency, []).append(package)
    return test_provider(reversed_graph)


def build_reverse_dependency_graph(
    graph: dict[str, list[str]], target: str, version: str,
    max_depth: int, filter_text: str,
) -> dict[str, list[str]]:
    """Найти прямых и транзитивных зависимых тем же BFS-обходом."""
    if target not in graph:
        raise ValueError(f"Пакет '{target}' не найден в построенном графе")
    return build_dependency_graph(
        target, version, max_depth, filter_text, reverse_provider(graph))


def print_reverse_graph(target: str, graph: dict[str, list[str]]) -> None:
    """Напечатать обратные рёбра от пакета к его зависимым."""
    print(f"Обратные зависимости пакета {target}:")
    edges = [(package, dependent) for package, dependents in graph.items()
             for dependent in dependents]
    if not edges:
        print("Обратных зависимостей не найдено.")
        return
    for package, dependent in edges:
        print(f"{package} <- {dependent}")


def main() -> int:
    """Загрузить настройки, построить и вывести граф."""
    arguments = parse_arguments()
    try:
        config = load_config(arguments.config)
        provider = configured_provider(config, arguments.config)
        package_name = arguments.package or config["package_name"]
        graph = build_dependency_graph(
            package_name, config["version"], config["max_depth"],
            config["filter"], provider)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    target = arguments.reverse_dependencies
    if target is None:
        print_graph(package_name, config["version"], graph)
        if config["ascii_tree"]:
            print_ascii_tree(package_name, graph)
        output_path = arguments.output or Path(config["output_file"])
        if not output_path.is_absolute():
            output_path = Path(__file__).resolve().parents[1] / output_path
        try:
            caption = (
                f"Версия корневого пакета {package_name}: "
                f"{config['version']}"
            )
            mermaid_path = write_visualization(
                graph, output_path, caption)
        except (OSError, ValueError) as error:
            print(f"Ошибка: {error}", file=sys.stderr)
            return 1
        print(f"Mermaid source: {mermaid_path}")
        print(f"SVG saved: {output_path}")
        return 0
    try:
        reverse_graph = build_reverse_dependency_graph(
            graph, target, config["version"], config["max_depth"],
            config["filter"])
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print_reverse_graph(target, reverse_graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
