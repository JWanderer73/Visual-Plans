# Visual Plan implementation plan

Build a local tool that turns a coding agent’s plan into two matching outputs. The agent returns the full Markdown plan in chat, and the reviewer opens a self-contained HTML preview to inspect the sequence of work, dependencies, and unresolved decisions.

## Architecture and tools

Implement the renderer as a Python library with a thin CLI. The library accepts a validated plan and returns Markdown and HTML strings. The CLI handles input, configuration, file writes, and browser launch. A future editor extension or MCP tool can call the same library.

| Component | Implementation |
| --- | --- |
| CLI | Python 3, `argparse`, and a `visual-plan` console entry point declared in `pyproject.toml` |
| Project tooling | Use `uv` to manage the Python environment, dependencies, tests, builds, and local CLI installation. Commit `uv.lock` alongside `pyproject.toml`. |
| Plan validation | A bundled, versioned JSON Schema checked with `jsonschema`, followed by checks for invalid references and dependency cycles |
| Rendering | Markdown and semantic HTML with embedded CSS and inline SVG for dependency diagrams. Escape plan text for each output context. |
| Preview launch | `pathlib` for file paths and `webbrowser` for opening a local file URI |
| Verification | `pytest` for renderer and CLI behavior, plus a browser review of representative plans |

## Command interface

```sh
visual-plan render plan.json --open
visual-plan render --stdin --open
visual-plan render plan.json --format json
visual-plan render plan.json --output review/plan.html
```

Accept either a file or standard input. By default, write the full Markdown to stdout and the absolute HTML path to stderr. In JSON mode, emit a single object on stdout containing `markdown`, `preview_path`, and `open_status`. Keep diagnostics on stderr.

Use a small user configuration file for theme, default layout, and browser-opening preference. Default to opening the browser only on request. Explicit CLI options take precedence over saved preferences.

## Plan contract

```json
{
  "schema_version": 1,
  "id": "account-export",
  "title": "Add account data export",
  "goal": "Let users download a copy of their account data.",
  "steps": [
    {
      "id": "contract",
      "title": "Define the export contract",
      "detail": "Specify the fields, file format, and authorization rules.",
      "outcome": "An agreed contract and an example export.",
      "depends_on": []
    },
    {
      "id": "endpoint",
      "title": "Implement the download endpoint",
      "detail": "Generate the export using the agreed contract.",
      "outcome": "An authenticated user can download their own data.",
      "depends_on": ["contract"]
    }
  ],
  "decisions": [
    {
      "step_id": "contract",
      "question": "Should the export include archived records?"
    }
  ]
}
```

Preserve array order as the author’s reading order. Draw an edge only for an explicit dependency. Keep plan and step IDs stable across revisions. Validate schema version, field types, unique step IDs, dependency references, cycles, and decision targets before writing any output. Identify the offending field or step in errors.

## Examples in a plan

Allow an optional ordered `examples` array on the plan and on each step. Use a plan-level example for a proposed final deliverable and a step-level example for an intermediate result. Each example has a type, a caption, and type-specific fields. Render the caption beside the example in both outputs. Label illustrative data as sample data.

| Type | Input | HTML preview | Markdown in chat |
| --- | --- | --- | --- |
| Plot | Line or bar chart, labeled axes with units where applicable, and named series of points | Generate and embed a static SVG with Matplotlib | Caption and table of the plotted values |
| Diagram | Labeled nodes and directed edges with optional labels | Render inline SVG using the dependency diagram layout code, with support for cycles in example diagrams | List the nodes and their labeled connections |
| Sample output | Literal text and optional language, such as JSON or CSV | Escaped, preformatted text preserving whitespace | Fenced block preserving the exact output |
| Table | Column headings and ordered rows | Semantic table with header cells | Markdown table with escaped cell values |

For example, the export-contract step could include this field:

```json
"examples": [
  {
    "type": "sample_output",
    "caption": "Sample CSV export for one active account",
    "language": "csv",
    "text": "account_id,status\n42,active"
  }
]
```

Validate each example before rendering, including row widths, plotted values, and diagram edge targets. Report the step and example index for invalid inputs. Generate visuals from the supplied data so both outputs convey the same values and relationships.

## Review experience

Render the title, goal, numbered steps, details, outcomes, dependencies, and decisions in Markdown so the conversation contains the complete plan.

In HTML, lead with the goal and an overview that links to full step details. Use a numbered sequence for linear work and a dependency diagram for branches and joins. Offer a list view with explicit dependency links for dense graphs and narrow screens. Place open decisions beside the steps they affect. Provide expandable details and print styling. Embed assets so the preview works offline.

## Storage and delivery

Store generated previews in a user cache directory by default. Scope each path by project and plan ID, using the repository root when available and the working directory otherwise. Encode or hash those identifiers into safe path components. Support an explicit output path for sharing or collecting the file as an artifact.

Write each revision to a temporary file in the destination directory and atomically replace the preview after rendering succeeds. The reviewer can refresh the same URL after a revision. Attempt browser launch after the write. If launch fails, report the failure separately and return the usable preview path and Markdown.

Install the CLI once per user so local shell-capable coding tools can invoke it across projects. Remote callers can collect the HTML through their own artifact mechanism. Natural-language triggers and agent-specific skills are follow-up integrations.

## Delivery milestones

1. **Working vertical slice.** Initialize a packaged Python project with uv. Declare runtime dependencies and put pytest in the development dependency group. Package the schema and implement file input, validation, and both renderers. Ship a linear example and document the working command in the README. Run it through the CLI and confirm the Markdown and HTML contain the same steps and outcomes.
2. **Visual review.** Implement branch and join layouts, decision placement, linked details, print styling, and the four example types. Review a branching fixture with all four types in an offline browser and in Markdown. Check plot units and values, diagram connections, table headings, and exact sample-output text against the input. Verify that a plan omitting examples still renders.
3. **Caller integration.** Add stdin, structured output, output-path selection, configuration, and optional browser launch. Verify a caller can parse stdout and recover the preview when the browser is unavailable.
4. **Revision and project handling.** Implement project-scoped caching and atomic file replacement. Verify that two projects can reuse a plan ID and that an invalid revision preserves the previous preview.
5. **Release verification.** From a clean checkout, run `uv sync --locked`, `uv run pytest`, and `uv build`. Install the resulting wheel with `uv tool install` and exercise the CLI from outside the checkout. Pipe in a plan, open it, revise it, and compare both outputs. Verify the README quickstart using a shipped example. Link the input schema and document CLI options, output locations, and browser behavior.

The release is ready when a local coding tool can pipe a plan into `visual-plan render --stdin --open`, capture the complete Markdown for chat, and open the corresponding HTML for human review.
