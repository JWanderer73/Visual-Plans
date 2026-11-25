"""Lay out directed graphs and render them as inline SVG."""

from collections import defaultdict
from dataclasses import dataclass
from graphlib import TopologicalSorter
from html import escape
from textwrap import wrap


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    number: int | None = None
    href: str | None = None


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""


def _ranks(nodes: list[Node], edges: list[Edge]) -> dict[str, int]:
    successors = {node.id: [] for node in nodes}
    for edge in edges:
        successors[edge.source].append(edge.target)

    # Back edges are routed around the rows and do not constrain the ranks.
    predecessors = {node.id: [] for node in nodes}
    visited = set()
    for root in successors:
        if root in visited:
            continue
        visited.add(root)
        active = {root}
        stack = [(root, iter(successors[root]))]
        while stack:
            source, targets = stack[-1]
            target = next(targets, None)
            if target is None:
                active.remove(source)
                stack.pop()
            elif target not in active:
                predecessors[target].append(source)
                if target not in visited:
                    visited.add(target)
                    active.add(target)
                    stack.append((target, iter(successors[target])))

    ranks = {}
    for node_id in TopologicalSorter(predecessors).static_order():
        ranks[node_id] = max((ranks[parent] + 1 for parent in predecessors[node_id]), default=0)
    return ranks


def _ports(edges: list[Edge], width: int) -> tuple[dict, dict]:
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    for index, edge in enumerate(edges):
        outgoing[edge.source].append(index)
        incoming[edge.target].append(index)

    def offsets(groups: dict) -> dict:
        return {
            index: width * (position / (len(group) + 1) - 0.5) * 0.8
            for group in groups.values()
            for position, index in enumerate(group, start=1)
        }

    return offsets(outgoing), offsets(incoming)


def diagram_svg(nodes: list[Node], edges: list[Edge], *, prefix: str, title: str) -> str:
    ranks = _ranks(nodes, edges)
    rows = defaultdict(list)
    labels = {}
    for node in nodes:
        rows[ranks[node.id]].append(node.id)
        labels[node.id] = wrap(" ".join(node.label.split()), width=27) or [""]

    box_width, horizontal_gap, vertical_gap, margin = 252, 34, 84, 18
    widest = max(map(len, rows.values()))
    grid_width = widest * box_width + (widest - 1) * horizontal_gap
    positions = {}
    top = margin
    for rank in range(len(rows)):
        row = rows[rank]
        row_width = len(row) * box_width + (len(row) - 1) * horizontal_gap
        left = margin + (grid_width - row_width) / 2
        height = 33 + 18 * max(len(labels[node_id]) for node_id in row)
        for node_id in row:
            positions[node_id] = (left, top, height)
            left += box_width + horizontal_gap
        top += height + vertical_gap

    marker = f"{prefix}-arrow"
    outgoing, incoming = _ports(edges, box_width)
    edge_shapes = []
    side_count = 0
    extra_width = 0
    for index, edge in enumerate(edges):
        source_x, source_y, source_height = positions[edge.source]
        target_x, target_y, _ = positions[edge.target]
        start_x = source_x + box_width / 2 + outgoing[index]
        end_x = target_x + box_width / 2 + incoming[index]
        start_y = source_y + source_height
        label_lines = wrap(" ".join(edge.label.split()), width=24)
        if ranks[edge.target] == ranks[edge.source] + 1:
            middle_y = (start_y + target_y) / 2
            path = f"M {start_x} {start_y} C {start_x} {middle_y}, {end_x} {middle_y}, {end_x} {target_y}"
            label_x, label_y = (start_x + end_x) / 2, middle_y - 9
        else:
            side_count += 1
            channel_x = grid_width + margin + 24 + 18 * side_count
            exit_y, entry_y = start_y + 20, target_y - 10
            path = f"M {start_x} {start_y} V {exit_y} H {channel_x} V {entry_y} H {end_x} V {target_y}"
            label_x, label_y = channel_x + 9, (exit_y + entry_y) / 2
            extra_width = max(extra_width, channel_x - grid_width + (180 if label_lines else margin))
        edge_shapes.append(
            f'<path class="graph-edge" d="{path}" marker-end="url(#{marker})">'
            f'<title>{escape(edge.label or (edge.source + " → " + edge.target))}</title></path>'
        )
        for line_index, line in enumerate(label_lines):
            anchor = "middle" if ranks[edge.target] == ranks[edge.source] + 1 else "start"
            edge_shapes.append(
                f'<text class="edge-label" x="{label_x}" y="{label_y + 15 * line_index}" '
                f'text-anchor="{anchor}">{escape(line)}</text>'
            )

    node_shapes = []
    for node in nodes:
        x, y, height = positions[node.id]
        name = f"{node.number}. {node.label}" if node.number is not None else node.label
        shape = [
            f'<title>{escape(name)}</title>',
            f'<rect class="node-box" x="{x}" y="{y}" width="{box_width}" height="{height}" rx="9"/>',
        ]
        if node.number is not None:
            shape.append(f'<text class="node-number" x="{x + 14}" y="{y + 29}">{node.number}.</text>')
        label_x = x + (43 if node.number is not None else 15)
        for index, line in enumerate(labels[node.id]):
            shape.append(f'<text class="node-label" x="{label_x}" y="{y + 29 + 18 * index}">{escape(line)}</text>')
        content = "".join(shape)
        if node.href is not None:
            content = f'<a href="{escape(node.href)}" aria-label="{escape(name)}">{content}</a>'
        else:
            content = f"<g>{content}</g>"
        node_shapes.append(content)

    width = grid_width + 2 * margin + extra_width
    height = top - vertical_gap + margin + (24 if side_count else 0)
    role = "group" if any(node.href is not None for node in nodes) else "img"
    return (
        f'<svg class="graph" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="{role}" aria-labelledby="{prefix}-title">'
        f'<title id="{prefix}-title">{escape(title)}</title>'
        f'<defs><marker id="{marker}" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto">'
        '<path class="edge-arrow" d="M 0 0 L 8 4 L 0 8 Z"/></marker></defs>'
        + "".join(edge_shapes + node_shapes)
        + "</svg>"
    )
