"""Проверить Mermaid, SVG и ASCII-дерево графа зависимостей."""

import importlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
visualization_module = importlib.import_module("visualization")


SAMPLE_GRAPH = {
    "A": ["B", "C"], "B": ["D"], "C": ["D"], "D": ["A"],
}


class VisualizationTests(unittest.TestCase):
    """Проверить текстовые и графические представления."""

    def test_mermaid_contains_nodes_and_edges(self) -> None:
        """Сформировать Mermaid flowchart со всеми рёбрами."""
        source = visualization_module.mermaid_source(SAMPLE_GRAPH)
        self.assertTrue(source.startswith("flowchart LR\n"))
        self.assertIn('N0["A"]', source)
        self.assertIn("N0 --> N1", source)
        self.assertIn("N3 --> N0", source)

    def test_mermaid_and_svg_show_versions_and_constraints(self) -> None:
        """Показать версии узлов и диапазоны на рёбрах."""
        versions = {"A": "1.2.3", "B": "2.0.0"}
        constraints = {("A", "B"): "[2.0.0, 3.0.0)"}
        graph = {"A": ["B"], "B": []}
        source = visualization_module.mermaid_source(
            graph, versions, constraints)
        self.assertIn('N0["A<br/>1.2.3"]', source)
        self.assertIn("N0 -->|[2.0.0, 3.0.0)| N1", source)
        svg = visualization_module.svg_source(graph, versions, constraints)
        self.assertIn(">2.0.0</text>", svg)
        self.assertIn(">[2.0.0, 3.0.0)</text>", svg)

    def test_ascii_tree_marks_cycles_and_shared_nodes(self) -> None:
        """Завершить обход цикла и отметить повтор узла."""
        tree = visualization_module.ascii_tree("A", SAMPLE_GRAPH)
        self.assertIn("|-- B", tree)
        self.assertIn("[already shown]", tree)

    def test_writes_svg_and_mermaid_files(self) -> None:
        """Сохранить SVG и Mermaid рядом и разобрать XML."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "graph.svg"
            mermaid_path = visualization_module.write_visualization(
                SAMPLE_GRAPH, output)
            self.assertTrue(mermaid_path.is_file())
            self.assertTrue(output.is_file())
            root = ElementTree.parse(output).getroot()
            mermaid_text = mermaid_path.read_text(encoding="utf-8")
            svg_edges = root.findall(
                ".//svg:path[@marker-end]",
                {"svg": "http://www.w3.org/2000/svg"})
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(len(svg_edges), 5)
        self.assertEqual(mermaid_text.count("-->"), 5)
        self.assertIn("N0 --> N1", mermaid_text)

    def test_empty_graph_writes_valid_svg(self) -> None:
        """Рендерить корректный пустой SVG для пустого графа."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "empty.svg"
            visualization_module.write_visualization({}, output)
            root = ElementTree.parse(output).getroot()
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")

    def test_requires_svg_extension(self) -> None:
        """Отклонить выходной путь с неверным расширением."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "graph.png"
            with self.assertRaisesRegex(ValueError, "расширение .svg"):
                visualization_module.write_visualization(SAMPLE_GRAPH, output)


if __name__ == "__main__":
    unittest.main()
