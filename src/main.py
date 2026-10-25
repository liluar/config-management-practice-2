"""Загрузка, проверка и печать параметров YAML-конфигурации."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
REQUIRED_KEYS = (
    "package_name",
    "repository",
    "test_mode",
    "version",
    "output_file",
    "ascii_tree",
    "max_depth",
    "filter",
)
STRING_KEYS = (
    "package_name",
    "repository",
    "version",
    "output_file",
)
MIN_DEPTH = 0


def parse_arguments() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Проверка YAML-конфигурации практической работы"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="путь к YAML-файлу конфигурации",
    )
    return parser.parse_args()


def read_yaml(path: Path) -> Any:
    """Прочитать YAML и вернуть разобранное значение."""
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
    """Проверить, что корнем YAML является отображение."""
    if not isinstance(data, dict):
        raise ValueError("Конфигурация должна быть YAML-отображением")
    return data


def validate_required_keys(config: dict[str, Any]) -> None:
    """Проверить наличие всех восьми параметров."""
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError("Отсутствуют параметры: " + ", ".join(missing))


def validate_strings(config: dict[str, Any]) -> None:
    """Проверить тип и непустое значение строковых параметров."""
    for key in STRING_KEYS:
        value = config[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Параметр '{key}' должен быть непустой строкой")
    if not isinstance(config["filter"], str):
        raise ValueError("Параметр 'filter' должен быть строкой")


def validate_booleans(config: dict[str, Any]) -> None:
    """Проверить логический тип параметров режима и дерева."""
    for key in ("test_mode", "ascii_tree"):
        if not isinstance(config[key], bool):
            raise ValueError(f"Параметр '{key}' должен быть true или false")


def validate_depth(config: dict[str, Any]) -> None:
    """Проверить неотрицательное целое значение глубины."""
    depth = config["max_depth"]
    if type(depth) is not int or depth < MIN_DEPTH:
        raise ValueError(
            f"Параметр 'max_depth' должен быть целым числом не меньше "
            f"{MIN_DEPTH}"
        )


def validate_config(data: Any) -> dict[str, Any]:
    """Проверить все значения и вернуть конфигурацию."""
    config = require_mapping(data)
    validate_required_keys(config)
    validate_strings(config)
    validate_booleans(config)
    validate_depth(config)
    return config


def load_config(path: Path) -> dict[str, Any]:
    """Загрузить YAML-файл и проверить его параметры."""
    return validate_config(read_yaml(path))


def print_config(config: dict[str, Any]) -> None:
    """Напечатать параметры в исходном порядке задания."""
    for key in REQUIRED_KEYS:
        print(f"{key}: {config[key]}")


def main() -> int:
    """Загрузить файл конфигурации и напечатать параметры."""
    arguments = parse_arguments()
    try:
        config = load_config(arguments.config)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print_config(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
