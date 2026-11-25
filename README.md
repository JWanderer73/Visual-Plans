# Visual Plans

Visual Plans turns one JSON plan into complete Markdown for chat and a self-contained HTML preview for review. The preview links the overview to step details and places open decisions beside the steps they affect.

## Quickstart

From the checkout, with Python 3.11 or later and uv installed, run the linear example.

```sh
uv sync --locked
uv run visual-plan render examples/linear.json --open
```

The [branching example](examples/branching.json) includes a plot, a cyclic diagram, literal CSV output, and a table. Render it to a file you can share.

```sh
uv run visual-plan render examples/branching.json --output review/plan.html
```

Install the CLI once per user from the checkout. From any project, pipe in a plan and capture its Markdown while opening the matching preview.

```sh
uv tool install .
visual-plan render --stdin --open < plan.json
```

## Inputs and outputs

Use the [version 1 JSON Schema](src/visual_plan/plan-v1.schema.json) or start with the [linear example](examples/linear.json). Keep the plan and step IDs stable across revisions. Step order sets the reading order. Each `depends_on` entry names a prerequisite step ID. Decisions specify a `step_id` and a `question`.

Plans and individual steps can each have an ordered `examples` array. Every example has a `type` and a `caption`.

| Type | Fields |
| --- | --- |
| `plot` | `chart` is `line` or `bar`. Both `x_axis` and `y_axis` have a `label` and an optional `unit`. Each entry in `series` has a `name` and ordered `points` with `x` and `y` values. Use numbers for all x values or text categories for all x values. Use numbers for y values. |
| `diagram` | `nodes` have an `id` and `label`. Directed `edges` have `from` and `to` node IDs and an optional `label`. Cycles are allowed in example diagrams. |
| `sample_output` | `text` holds literal output. The optional `language` names the fenced block's syntax. |
| `table` | `columns` lists the headings. Each entry in `rows` supplies one scalar value per column. |

By default, stdout receives the entire Markdown plan and stderr receives the absolute HTML path. With `--format json`, stdout receives one JSON object with `markdown`, `preview_path`, and `open_status`. The status is `not_requested`, `opened`, or `failed`. Browser failures produce a diagnostic on stderr and leave the saved preview and a successful exit status available to the caller. Invalid plans and write failures exit nonzero with diagnostics on stderr.

By default, previews live under the operating system's per-user cache directory. The CLI keys each preview by the Git root of the working directory, or the working directory itself outside Git, and by the plan ID. Rendering a valid revision atomically replaces the previous preview. Refresh the existing browser tab to see the update. Use `--output PATH` to select a different location or collect the file on a remote runner.

## Options and configuration

| Option | Behavior |
| --- | --- |
| `PLAN` or `--stdin` | Read a UTF-8 JSON file or standard input. |
| `--format markdown\|json` | Select the stdout format. |
| `--output PATH` | Save the preview at an explicit path. |
| `--open` or `--no-open` | Enable or disable browser launch after saving. |
| `--theme system\|light\|dark` | Control the preview's color scheme. |
| `--layout auto\|diagram\|list` | Select the overview. Automatic layout uses a numbered sequence for linear plans, a diagram for branches and joins, and the list first for dense graphs. Narrow screens and print use the linked list. |
| `--config PATH` | Read settings from a specific TOML file. |

Save preferences in `visual-plan/config.toml` under your user configuration directory. Typical paths are `~/.config/visual-plan/config.toml` on Linux and `~/Library/Application Support/visual-plan/config.toml` on macOS.

```toml
theme = "system"
layout = "auto"
open_browser = false
```

These are also the defaults. Explicit CLI options override saved settings.

## Library and development

```python
from visual_plan import load_plan, render_plan

plan = load_plan(source_json)
rendered = render_plan(plan, theme="light")
markdown, html = rendered.markdown, rendered.html
```

Use `validate_plan` when the input is already a Python dictionary. It and `load_plan` raise `PlanError` for invalid input. `render_markdown` and `render_html` can render either format individually.

```sh
uv sync --locked
uv run pytest
uv build
```

See the original [implementation plan](docs/implementation-plan.md) for the design and release checks.
