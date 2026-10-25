"""Тесты загрузки и проверки YAML-конфигурации."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import load_config, main, validate_config


VALID_CONFIG = {
    "package_name": "A",
    "repository": "test_graph.json",
    "test_mode": True,
    "version": "1.0.0",
    "output_file": "output/dependencies.svg",
    "ascii_tree": True,
    "max_depth": 5,
    "filter": "",
}


class ConfigTests(unittest.TestCase):
    """Проверить валидные и ошибочные варианты конфигурации."""

    def write_config(self, content: str) -> Path:
        """Создать временный YAML-файл и удалить его после теста."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        )
        handle.write(content)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_load_valid_config(self) -> None:
        """Загрузить все восемь параметров."""
        path = self.write_config(
            "package_name: A\nrepository: test_graph.json\n"
            "test_mode: true\nversion: 1.0.0\n"
            "output_file: output/dependencies.svg\n"
            "ascii_tree: true\nmax_depth: 5\nfilter: ''\n"
        )
        self.assertEqual(load_config(path), VALID_CONFIG)

    def test_missing_file(self) -> None:
        """Сообщить об отсутствующем файле."""
        with self.assertRaisesRegex(ValueError, "не найден"):
            load_config(Path("missing-config.yaml"))

    def test_invalid_yaml(self) -> None:
        """Отклонить синтаксически неверный YAML."""
        path = self.write_config("package_name: [broken\n")
        with self.assertRaisesRegex(ValueError, "Некорректный YAML"):
            load_config(path)

    def test_missing_key(self) -> None:
        """Назвать отсутствующий обязательный параметр."""
        config = dict(VALID_CONFIG)
        del config["version"]
        with self.assertRaisesRegex(ValueError, "version"):
            validate_config(config)

    def test_string_parameter_rejects_number(self) -> None:
        """Отклонить неверный тип строкового поля."""
        config = dict(VALID_CONFIG, package_name=7)
        with self.assertRaisesRegex(ValueError, "package_name"):
            validate_config(config)

    def test_boolean_parameter_rejects_string(self) -> None:
        """Отклонить текст вместо логического значения."""
        config = dict(VALID_CONFIG, test_mode="true")
        with self.assertRaisesRegex(ValueError, "test_mode"):
            validate_config(config)

    def test_depth_rejects_boolean(self) -> None:
        """Отклонить bool, хотя в Python он является подклассом int."""
        config = dict(VALID_CONFIG, max_depth=True)
        with self.assertRaisesRegex(ValueError, "max_depth"):
            validate_config(config)

    def test_depth_rejects_zero(self) -> None:
        """Отклонить глубину меньше минимальной."""
        config = dict(VALID_CONFIG, max_depth=0)
        with self.assertRaisesRegex(ValueError, "не меньше"):
            validate_config(config)

    def test_empty_filter_is_allowed(self) -> None:
        """Разрешить пустой фильтр для отключения фильтрации."""
        self.assertEqual(validate_config(VALID_CONFIG)["filter"], "")

    def test_main_prints_key_values(self) -> None:
        """Напечатать параметры конфигурации в формате ключ-значение."""
        path = self.write_config(
            "package_name: A\nrepository: test_graph.json\n"
            "test_mode: true\nversion: 1.0.0\n"
            "output_file: output/dependencies.svg\n"
            "ascii_tree: true\nmax_depth: 5\nfilter: ''\n"
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with contextlib.redirect_stderr(io.StringIO()):
                result = main_for(path)
        self.assertEqual(result, 0)
        self.assertIn("package_name: A", output.getvalue())
        self.assertIn("filter: ", output.getvalue())


def main_for(path: Path) -> int:
    """Вызвать main с переопределёнными аргументами."""
    from unittest.mock import patch

    with patch("sys.argv", ["main.py", "--config", str(path)]):
        return main()


if __name__ == "__main__":
    unittest.main()
