"""Render a validated plan for chat and browser review."""

from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from html import escape
from importlib.resources import files

from .diagrams import Edge, Node, diagram_svg
from .plots import plot_image
from .text import cell_value, markdown_fence, markdown_table, markdown_text, plot_rows
from .validation import Plan

THEMES = ("system", "light", "dark")
LAYOUTS = ("auto", "diagram", "list")


@dataclass(frozen=True)
class RenderedPlan:
    markdown: str
    html: str


def _steps(plan: Plan) -> dict[str, tuple[int, dict]]:
    return {step["id"]: (index, step) for index, step in enumerate(plan["steps"], start=1)}


def _step_name(steps: dict, step_id: str) -> str:
    index, step = steps[step_id]
    return f"{index}. {step['title']}"


def _markdown_step_name(steps: dict, step_id: str) -> str:
    index, step = steps[step_id]
    return f"{index}. {markdown_text(step['title'], line_break=' ')}"


def _anchor(step_id: str) -> str:
    return "step-" + sha256(step_id.encode("utf-8")).hexdigest()


def _diagram_content(example: dict) -> tuple[list[Node], list[Edge]]:
    return (
        [Node(node["id"], node["label"]) for node in example["nodes"]],
        [Edge(edge["from"], edge["to"], edge.get("label", "")) for edge in example["edges"]],
    )


def _diagram_connections(nodes: list[Node], edges: list[Edge]) -> list[str]:
    names = {node.id: f"{node.label} ({node.id})" for node in nodes}
    return [
        f"{names[edge.source]} → {names[edge.target]}" + (f" · {edge.label}" if edge.label else "")
        for edge in edges
    ]


def _markdown_example(example: dict) -> str:
    caption = f"**Sample data** · {markdown_text(example['caption'])}"
    match example["type"]:
        case "table":
            content = markdown_table(example["columns"], example["rows"])
        case "plot":
            kind = example["chart"].capitalize()
            content = f"{kind} chart\n\n" + markdown_table(*plot_rows(example))
        case "diagram":
            nodes, edges = _diagram_content(example)
            node_list = "\n".join(f"- {markdown_text(node.label)} ({markdown_text(node.id)})" for node in nodes)
            connections = "\n".join(f"- {markdown_text(link)}" for link in _diagram_connections(nodes, edges))
            content = f"**Nodes**\n\n{node_list}\n\n**Connections**\n\n{connections or 'None'}"
        case "sample_output":
            content = markdown_fence(example["text"], example.get("language", ""))
    return f"{caption}\n\n{content}"


def render_markdown(plan: Plan) -> str:
    """Return the complete Markdown review of a validated plan."""
    steps = _steps(plan)
    blocks = [
        f"# {markdown_text(plan['title'], line_break=' ')}",
        f"**Goal**\n\n{markdown_text(plan['goal'])}",
    ]
    if plan.get("examples"):
        blocks.append("## Examples")
        blocks.extend(_markdown_example(example) for example in plan["examples"])
    blocks.append("## Steps")
    for number, step in steps.values():
        blocks.extend([
            f"### {number}. {markdown_text(step['title'], line_break=' ')}",
            markdown_text(step["detail"]),
            f"**Outcome** · {markdown_text(step['outcome'])}",
        ])
        dependencies = " · ".join(_markdown_step_name(steps, key) for key in step["depends_on"])
        blocks.append(f"**Depends on** · {dependencies or 'None'}")
        blocks.extend(_markdown_example(example) for example in step.get("examples", []))
    if plan.get("decisions"):
        decisions = [
            f"- **{_markdown_step_name(steps, item['step_id'])}** · {markdown_text(item['question'])}"
            for item in plan["decisions"]
        ]
        blocks.extend(["## Open decisions", "\n".join(decisions)])
    return "\n\n".join(blocks) + "\n"


def _html_table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f'<th scope="col">{escape(heading)}</th>' for heading in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(cell_value(value))}</td>" for value in row)
        body.append(f"<tr>{cells}</tr>")
    return (
        '<div class="table-scroll"><table>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
        "</table></div>"
    )


def _html_list(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def _html_example(example: dict, prefix: str) -> str:
    caption = f'<figcaption><span>Sample data</span>{escape(example["caption"])}</figcaption>'
    match example["type"]:
        case "table":
            content = _html_table(example["columns"], example["rows"])
        case "plot":
            axes, _ = plot_rows(example)
            alt = f"{example['chart'].capitalize()} chart of {axes[2]} by {axes[1]}"
            content = (
                f'<img class="plot" src="{plot_image(example)}" alt="{escape(alt)}">'
                f'<details class="example-details"><summary>Plotted values</summary>{_html_table(*plot_rows(example))}</details>'
            )
        case "diagram":
            nodes, edges = _diagram_content(example)
            svg = diagram_svg(nodes, edges, prefix=prefix, title=example["caption"])
            node_list = _html_list([f"{node.label} ({node.id})" for node in nodes])
            connections = _html_list(_diagram_connections(nodes, edges)) if edges else "<p>None</p>"
            content = (
                f'<div class="graph-scroll">{svg}</div>'
                '<details class="example-details"><summary>Nodes and connections</summary>'
                f"<h4>Nodes</h4>{node_list}<h4>Connections</h4>{connections}</details>"
            )
        case "sample_output":
            literal = escape(example["text"], quote=False).replace("\r", "&#13;")
            language = example.get("language")
            attribute = f' class="language-{escape(language)}"' if language else ""
            content = f"<pre><code{attribute}>{literal}</code></pre>"
    return f"<figure>{caption}{content}</figure>"


def _step_link(steps: dict, step_id: str, *, number: bool = True) -> str:
    label = _step_name(steps, step_id) if number else steps[step_id][1]["title"]
    return f'<a href="#{_anchor(step_id)}">{escape(label)}</a>'


def _dependency_links(steps: dict, step: dict) -> str:
    return ", ".join(_step_link(steps, dependency) for dependency in step["depends_on"]) or "None"


def _overview(steps: dict, layout: str) -> str:
    sequence = []
    listing = []
    edges = []
    preceding = None
    linear = True
    for step_id, (number, step) in steps.items():
        dependencies = step["depends_on"]
        linear = linear and (not dependencies or dependencies == [preceding])
        preceding = step_id
        link = _step_link(steps, step_id, number=False)
        sequence.append(f"<li>{link}</li>")
        listing.append(f"<li>{link}<small>Depends on · {_dependency_links(steps, step)}</small></li>")
        edges.extend(Edge(dependency, step_id) for dependency in dependencies)

    list_view = (
        '<div class="overview-list" id="overview-list"><ol>'
        + "".join(listing)
        + "</ol></div>"
    )
    if layout == "list":
        return f'<nav aria-labelledby="overview-title"><h2 id="overview-title">Overview</h2>{list_view}</nav>'

    if layout == "auto" and linear:
        graphic_view = '<ol class="sequence">' + "".join(sequence) + "</ol>"
        graphic_label = "Sequence"
    else:
        nodes = [
            Node(step_id, step["title"], number, f"#{_anchor(step_id)}")
            for step_id, (number, step) in steps.items()
        ]
        svg = diagram_svg(nodes, edges, prefix="dependencies", title="Step dependencies")
        graphic_view = f'<div class="graph-scroll">{svg}</div>'
        graphic_label = "Diagram"

    dense = layout == "auto" and not linear and (len(steps) > 12 or len(edges) > 16)
    graphic_checked = "" if dense else " checked"
    list_checked = " checked" if dense else ""
    return (
        '<nav class="switchable" aria-labelledby="overview-title"><h2 id="overview-title">Overview</h2>'
        '<fieldset><legend class="sr-only">Overview layout</legend>'
        f'<input type="radio" name="overview" id="show-graphic" aria-controls="overview-graphic"{graphic_checked}>'
        f'<label for="show-graphic">{graphic_label}</label>'
        f'<input type="radio" name="overview" id="show-list" aria-controls="overview-list"{list_checked}>'
        '<label for="show-list">List</label>'
        f'<div class="overview-graphic" id="overview-graphic">{graphic_view}</div>{list_view}</fieldset></nav>'
    )


def _html_steps(steps: dict, decisions: list[dict]) -> str:
    questions = defaultdict(list)
    for decision in decisions:
        questions[decision["step_id"]].append(decision["question"])
    sections = []
    for step_id, (number, step) in steps.items():
        examples = "".join(
            _html_example(example, f"step-{number}-example-{index}")
            for index, example in enumerate(step.get("examples", []))
        )
        open_decisions = ""
        if questions[step_id]:
            open_decisions = (
                '<aside class="decisions"><h4>Open decisions</h4>'
                f"{_html_list(questions[step_id])}</aside>"
            )
        sections.append(
            f'<details class="step" id="{_anchor(step_id)}" open><summary>'
            f'<span class="step-number">{number}.</span> <span>{escape(step["title"])}</span>'
            '</summary><div class="step-body">'
            f'<p class="prose">{escape(step["detail"])}</p>'
            '<dl><dt>Outcome</dt>'
            f'<dd class="prose">{escape(step["outcome"])}</dd>'
            '<dt>Depends on</dt>'
            f'<dd>{_dependency_links(steps, step)}</dd></dl>'
            f"{open_decisions}{examples}</div></details>"
        )
    return "".join(sections)


@cache
def _asset(name: str) -> str:
    return files("visual_plan").joinpath(name).read_text(encoding="utf-8")


def render_html(plan: Plan, *, theme: str = "system", layout: str = "auto") -> str:
    """Return an offline HTML review of a validated plan."""
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}")
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}")
    steps = _steps(plan)
    title = escape(plan["title"])
    examples = "".join(
        _html_example(example, f"plan-example-{index}")
        for index, example in enumerate(plan.get("examples", []))
    )
    examples_section = f'<section aria-labelledby="examples-title"><h2 id="examples-title">Examples</h2>{examples}</section>' if examples else ""
    return (
        '<!doctype html>\n<html lang="en"'
        f' data-theme="{theme}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_asset('preview.css')}</style></head><body>"
        '<main class="page"><header class="hero"><h1>'
        f'{title}</h1><p class="goal">{escape(plan["goal"])}</p></header>'
        f"{_overview(steps, layout)}{examples_section}"
        '<section aria-labelledby="steps-title"><h2 id="steps-title">Steps</h2>'
        f"{_html_steps(steps, plan.get('decisions', []))}</section></main>"
        f"<script>{_asset('preview.js')}</script></body></html>\n"
    )


def render_plan(plan: Plan, *, theme: str = "system", layout: str = "auto") -> RenderedPlan:
    """Render both formats from a plan returned by load_plan or validate_plan."""
    return RenderedPlan(render_markdown(plan), render_html(plan, theme=theme, layout=layout))
