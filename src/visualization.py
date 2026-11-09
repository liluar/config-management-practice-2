"""Генерация Mermaid, SVG и ASCII-представлений графа."""

from __future__ import annotations

import html
from collections import deque
from pathlib import Path


MERMAID_HEADER = "flowchart LR"
SVG_MARGIN = 48
SVG_NODE_HEIGHT = 48
SVG_MIN_NODE_WIDTH = 112
SVG_CHAR_WIDTH = 8
SVG_HORIZONTAL_PADDING = 24
SVG_HORIZONTAL_GAP = 96
SVG_VERTICAL_GAP = 48
SVG_FONT_SIZE = 14
SVG_CURVE_OFFSET = 36
SVG_CYCLE_OFFSET = 24
SVG_CAPTION_HEIGHT = 38


def mermaid_source(
    graph: dict[str, list[str]], caption: str = ""
) -> str:
    """Сформировать текст Mermaid с устойчивыми идентификаторами узлов."""
    names = list(graph)
    identifiers = {name: f"N{index}" for index, name in enumerate(names)}
    lines = [MERMAID_HEADER]
    for name in names:
        label = html.escape(name, quote=True)
        lines.append(f'    {identifiers[name]}["{label}"]')
    for package, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in identifiers:
                identifiers[dependency] = f"N{len(identifiers)}"
                label = html.escape(dependency, quote=True)
                lines.append(f'    {identifiers[dependency]}["{label}"]')
            lines.append(f"    {identifiers[package]} --> "
                         f"{identifiers[dependency]}")
    return "\n".join(lines) + "\n"


def node_levels(graph: dict[str, list[str]]) -> dict[str, int]:
    """Назначить узлам минимальные уровни обходом в ширину."""
    if not graph:
        return {}
    root = next(iter(graph))
    levels = {root: 0}
    queue = deque([root])
    while queue:
        package = queue.popleft()
        for dependency in graph.get(package, []):
            if dependency not in levels:
                levels[dependency] = levels[package] + 1
                queue.append(dependency)
    next_level = max(levels.values(), default=0) + 1
    for package in graph:
        if package not in levels:
            levels[package] = next_level
            next_level += 1
    return levels


def node_width(package: str) -> int:
    """Оценить ширину SVG-узла по длине имени пакета."""
    text_width = len(package) * SVG_CHAR_WIDTH
    return max(SVG_MIN_NODE_WIDTH, text_width + SVG_HORIZONTAL_PADDING * 2)


def layout_nodes(
    graph: dict[str, list[str]],
) -> tuple[dict[str, tuple[int, int, int]], int, int]:
    """Разместить узлы по уровням графа слева направо."""
    if not graph:
        empty_width = SVG_MARGIN * 2 + SVG_MIN_NODE_WIDTH
        empty_height = SVG_MARGIN * 2 + SVG_NODE_HEIGHT
        return {}, empty_width, empty_height
    levels = node_levels(graph)
    columns: dict[int, list[str]] = {}
    for package, level in levels.items():
        columns.setdefault(level, []).append(package)
    column_widths = {
        level: max(node_width(package) for package in packages)
        for level, packages in columns.items()
    }
    max_rows = max((len(packages) for packages in columns.values()), default=1)
    height = (SVG_MARGIN * 2 + max_rows * SVG_NODE_HEIGHT
              + (max_rows - 1) * SVG_VERTICAL_GAP)
    positions = {}
    column_x = SVG_MARGIN
    for level, packages in columns.items():
        for row, package in enumerate(packages):
            width = node_width(package)
            x = column_x + (column_widths[level] - width) // 2
            y = SVG_MARGIN + row * (SVG_NODE_HEIGHT + SVG_VERTICAL_GAP)
            positions[package] = (x, y, width)
        column_x += column_widths[level] + SVG_HORIZONTAL_GAP
    width = column_x - SVG_HORIZONTAL_GAP + SVG_MARGIN
    return positions, width, height


def edge_svg(
    source: tuple[int, int, int], target: tuple[int, int, int],
) -> str:
    """Сформировать SVG-путь со стрелкой между двумя узлами."""
    source_x, source_y, source_width = source
    target_x, target_y, target_width = target
    start_y = source_y + SVG_NODE_HEIGHT // 2
    end_y = target_y + SVG_NODE_HEIGHT // 2
    if target_x > source_x:
        start_x = source_x + source_width
        end_x = target_x
        direction = 1
        first_y = start_y
        second_y = end_y
    else:
        start_x = source_x
        end_x = target_x + target_width
        direction = -1
        lane_y = max(0, min(source_y, target_y) - SVG_CYCLE_OFFSET)
        first_y = lane_y
        second_y = lane_y
    first_control = start_x + direction * SVG_CURVE_OFFSET
    second_control = end_x - direction * SVG_CURVE_OFFSET
    return (
        f'<path d="M {start_x} {start_y} C {first_control} {first_y}, '
        f'{second_control} {second_y}, {end_x} {end_y}" '
        'fill="none" stroke="#64748b" stroke-width="2" '
        'marker-end="url(#arrow)" />'
    )


def svg_source(graph: dict[str, list[str]], caption: str = "") -> str:
    """Сформировать автономное SVG-изображение направленного графа."""
    positions, width, chart_height = layout_nodes(graph)
    caption_height = SVG_CAPTION_HEIGHT if caption else 0
    height = chart_height + caption_height
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="8" refY="5" orient="auto" markerUnits="strokeWidth">',
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />',
        '</marker></defs>',
        '<rect width="100%" height="100%" fill="#ffffff" />',
    ]
    for package, dependencies in graph.items():
        for dependency in dependencies:
            lines.append(edge_svg(positions[package], positions[dependency]))
    for package, (x, y, width) in positions.items():
        label = html.escape(package)
        text_y = y + SVG_NODE_HEIGHT // 2 + SVG_FONT_SIZE // 2
        lines.extend([
            f'<rect x="{x}" y="{y}" width="{width}" '
            f'height="{SVG_NODE_HEIGHT}" rx="9" fill="#f1f5f9" '
            'stroke="#334155" stroke-width="1.5" />',
            f'<text x="{x + width // 2}" y="{text_y}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="{SVG_FONT_SIZE}" '
            f'fill="#0f172a">{label}</text>',
        ])
    if caption:
        caption_y = chart_height + caption_height // 2 + SVG_FONT_SIZE // 2
        lines.append(
            f'<text x="{width // 2}" y="{caption_y}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="{SVG_FONT_SIZE}" '
            f'fill="#334155">{html.escape(caption)}</text>'
        )
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def write_visualization(
    graph: dict[str, list[str]], output_path: Path, caption: str = "",
) -> Path:
    """Сохранить SVG и Mermaid-файл рядом; вернуть путь к Mermaid."""
    if output_path.suffix.lower() != ".svg":
        raise ValueError("Путь output_file должен иметь расширение .svg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mermaid_path = output_path.with_suffix(".mmd")
    mermaid_path.write_text(
        mermaid_source(graph, caption), encoding="utf-8")
    output_path.write_text(svg_source(graph, caption), encoding="utf-8")
    return mermaid_path


def ascii_tree(root: str, graph: dict[str, list[str]]) -> str:
    """Сформировать ASCII-дерево с метками повторов и циклов."""
    lines = [root]
    visited = {root}

    def visit(package: str, prefix: str) -> None:
        """Рекурсивно вывести ветви узла без повторного обхода."""
        dependencies = graph.get(package, [])
        for index, dependency in enumerate(dependencies):
            last = index == len(dependencies) - 1
            branch = "`-- " if last else "|-- "
            repeated = dependency in visited
            suffix = " [already shown]" if repeated else ""
            lines.append(f"{prefix}{branch}{dependency}{suffix}")
            if not repeated:
                visited.add(dependency)
                continuation = "    " if last else "|   "
                visit(dependency, prefix + continuation)

    visit(root, "")
    return "\n".join(lines)


def print_ascii_tree(root: str, graph: dict[str, list[str]]) -> None:
    """Напечатать ASCII-дерево зависимостей."""
    print("Зависимости в виде ASCII-дерева:")
    print(ascii_tree(root, graph))
