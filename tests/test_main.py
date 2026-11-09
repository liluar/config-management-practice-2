"""Проверить конфигурацию, граф зависимостей и тестовый режим."""

import contextlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
main_module = importlib.import_module("main")

VALID_CONFIG = {
    "package_name": "A", "repository": "test_graph.json",
    "test_mode": True, "version": "1.0.0",
    "output_file": "output/dependencies.svg", "ascii_tree": True,
    "max_depth": 5, "filter": "",
}


class ConfigTests(unittest.TestCase):
    """Проверить загрузку и валидацию YAML."""

    def write_config(self, content: str) -> Path:
        """Создать временный конфигурационный файл."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False)
        handle.write(content)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_load_valid_config(self) -> None:
        """Загрузить восемь параметров конфигурации."""
        content = ("package_name: A\nrepository: test_graph.json\n"
                   "test_mode: true\nversion: 1.0.0\n"
                   "output_file: output/dependencies.svg\n"
                   "ascii_tree: true\nmax_depth: 5\nfilter: ''\n")
        config = main_module.load_config(self.write_config(content))
        self.assertEqual(config, VALID_CONFIG)

    def test_missing_file_and_key(self) -> None:
        """Отклонить отсутствующий файл и обязательный параметр."""
        with self.assertRaisesRegex(ValueError, "не найден"):
            main_module.load_config(Path("missing-config.yaml"))
        config = dict(VALID_CONFIG)
        del config["version"]
        with self.assertRaisesRegex(ValueError, "version"):
            main_module.validate_config(config)

    def test_invalid_values(self) -> None:
        """Отклонить неверные типы параметров и глубину."""
        cases = (({"package_name": 7}, "package_name"),
                 ({"test_mode": "true"}, "test_mode"),
                 ({"max_depth": True}, "max_depth"),
                 ({"max_depth": -1}, "max_depth"),
                 ({"filter": False}, "filter"))
        for changes, message in cases:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    main_module.validate_config(dict(VALID_CONFIG, **changes))


class GraphTests(unittest.TestCase):
    """Проверить BFS с рекурсией, глубиной, фильтром и циклами."""

    def make_provider(self):
        """Создать поставщик тестовых зависимостей."""
        data = {"A": ["B", "C"], "B": ["D", "E"],
                "C": ["E", "F"], "D": ["A"],
                "E": ["G"], "F": [], "G": []}
        return main_module.test_provider(data)

    def build(self, depth: int = 5, filter_text: str = "") -> dict:
        """Запустить обход тестового графа."""
        provider = self.make_provider()
        return main_module.build_dependency_graph(
            "A", "1.0.0", depth, filter_text, provider)

    def test_recursive_bfs_and_cycle(self) -> None:
        """Обойти ветви по ширине, сохранив цикл A-D-A."""
        self.assertEqual(self.build(), {
            "A": ["B", "C"], "B": ["D", "E"],
            "C": ["E", "F"], "D": ["A"], "E": ["G"],
            "F": [], "G": [],
        })

    def test_max_depth(self) -> None:
        """Ограничить раскрытие узлов заданным числом переходов."""
        self.assertEqual(self.build(depth=1), {
            "A": ["B", "C"], "B": [], "C": []})
        self.assertEqual(self.build(depth=0), {"A": []})

    def test_collects_versions_and_edge_ranges(self) -> None:
        """Собрать версии узлов и требования зависимостей."""
        versions = {}
        constraints = {}
        main_module.build_dependency_graph(
            "A", "2.0.0", 1, "", self.make_provider(),
            versions, constraints)
        self.assertEqual(versions["A"], "2.0.0")
        self.assertEqual(versions["B"], main_module.TEST_VERSION)
        self.assertEqual(constraints[("A", "B")], "1.0.0")

    def test_substring_filter(self) -> None:
        """Исключить пакеты с совпадающей подстрокой без регистра."""
        self.assertEqual(self.build(filter_text="c"), {
            "A": ["B"], "B": ["D", "E"], "D": ["A"],
            "E": ["G"], "G": []})

    def test_read_graph_and_cli_test_mode(self) -> None:
        """Загрузить локальный граф и создать stage-5 изображения."""
        project = Path(__file__).resolve().parents[1]
        config = project / "config" / "test_mode.yaml"
        graph_path = config.parent / "test_graph.json"
        graph = main_module.read_test_graph(graph_path)
        self.assertEqual(graph["A"], ["B", "C"])
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "graph.svg"
            output = io.StringIO()
            args = ["main.py", "--config", str(config), "--package", "C",
                    "--output", str(output_path)]
            with contextlib.redirect_stdout(output):
                with patch("sys.argv", args):
                    self.assertEqual(main_module.main(), 0)
            self.assertTrue(output_path.is_file())
            self.assertTrue(output_path.with_suffix(".mmd").is_file())
            self.assertIn("C -> E", output.getvalue())
            self.assertIn("ASCII-дерева", output.getvalue())

    def test_reverse_dependencies_include_transitive_and_cycles(self) -> None:
        """Найти всех зависимых и остановиться на цикле."""
        graph = self.build()
        reverse = main_module.build_reverse_dependency_graph(
            graph, "G", "1.0.0", 5, "")
        self.assertEqual(reverse["G"], ["E"])
        self.assertEqual(reverse["E"], ["B", "C"])
        self.assertEqual(reverse["C"], ["A"])
        self.assertEqual(reverse["D"], ["B"])

    def test_reverse_mode_prints_edges(self) -> None:
        """Вывести обратные рёбра для выбранного тестового пакета."""
        config = Path(__file__).resolve().parents[1]
        config = config / "config" / "test_mode.yaml"
        output = io.StringIO()
        args = ["main.py", "--config", str(config),
                "--reverse-dependencies", "G"]
        with contextlib.redirect_stdout(output):
            with patch("sys.argv", args):
                self.assertEqual(main_module.main(), 0)
        self.assertIn("G <- E", output.getvalue())
        self.assertIn("E <- B", output.getvalue())
        self.assertIn("C <- A", output.getvalue())

    def test_reverse_depth_and_direct_dependent(self) -> None:
        """Ограничить глубину и показать прямого зависимого."""
        graph = self.build()
        direct = main_module.build_reverse_dependency_graph(
            graph, "F", "1.0.0", 1, "")
        self.assertEqual(direct, {"F": ["C"], "C": []})
        limited = main_module.build_reverse_dependency_graph(
            graph, "G", "1.0.0", 1, "")
        self.assertEqual(limited, {"G": ["E"], "E": []})

    def test_reverse_mode_rejects_missing_target(self) -> None:
        """Сообщить о пакете вне построенного графа."""
        with self.assertRaisesRegex(ValueError, "не найден"):
            main_module.build_reverse_dependency_graph(
                self.build(), "Z", "1.0.0", 5, "")

    def test_graph_rejects_invalid_names(self) -> None:
        """Требовать большие латинские буквы в файле графа."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps({"Alpha": ["B"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "имя"):
                main_module.read_test_graph(path)


if __name__ == "__main__":
    unittest.main()
