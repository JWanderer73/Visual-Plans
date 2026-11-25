# Visual Plans

Visual Plans is a planned Python CLI for reviewing a coding agent’s proposal. One structured plan produces a Markdown response for chat and a self-contained HTML preview for the reviewer. The preview can show step dependencies, open decisions, sample plots, diagrams, output, and tables.

## Project status

This repository currently contains the [implementation plan](docs/implementation-plan.md). It describes the input format, renderer, CLI behavior, and delivery milestones. The first milestone is a working example that produces both outputs from one JSON file.

## Planned development workflow

The project will use uv for Python packaging and dependency management. Once the first milestone lands, the intended workflow from the repository root is:

```sh
uv sync --locked
uv run visual-plan render examples/linear.json --open
uv run pytest
```

For use across projects, the planned installation command is `uv tool install .` from the checkout. A coding tool can then pipe a plan to `visual-plan render --stdin --open` and capture the Markdown from stdout while the browser opens the visual preview.
