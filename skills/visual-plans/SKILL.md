---
name: visual-plans
description: Create or revise a coding plan as matching Markdown and a Visual Plans browser preview. Use when the user asks for a visual plan, browser review of a plan, or changes based on Visual Plans feedback.
---

# Visual Plans

## Draft the plan

Inspect the target repository and plan the requested work. Keep the detail proportional to the task and include relevant design choices, constraints, tradeoffs, tests, and open decisions. Use these prompts to fill gaps in the plan where they matter.

- **Inputs** — Identify what the planned code will consume. Name the datasets, files, APIs, configuration, or user inputs and describe the fields, formats, versions, or assumptions that affect the work. Mark unconfirmed sources as open decisions when the choice matters.
- **Execution order** — Identify the entry point and the files, scripts, jobs, or stages that run. Show their order and what they pass downstream. Distinguish execution order from implementation order when they differ. Describe parallel branches, joins, or conditional paths where they affect the pipeline. For work with a single entry point, describe its actual execution flow.
- **Outputs** — Describe what the work will produce and where it will go. Give expected file paths, formats, table columns, plot axes, API responses, or other acceptance details when relevant. Include a small sample table, plot, diagram, or literal output when it helps the reviewer understand the deliverable. Label illustrative values as sample data.

Use the prompts within the appropriate steps and omit details with no bearing on the task. A plan for a small UI fix can describe its behavior and verification without a dataset or a multi-file pipeline.

## Render and review

Use the [Visual Plan v1 schema](references/plan-v1.schema.json). Write a single JSON plan with a stable plan ID and step IDs. Put implementation details and outcomes in the steps, use `depends_on` for actual prerequisites, and attach examples and unresolved questions to the work they affect. Place a deliverable example at plan level when it describes the overall result.

Keep the JSON in a writable location you can reuse across feedback rounds. Run `visual-plan` from the target repository. Use a stable preview path such as the one supplied in this example.

```sh
visual-plan render "$plan_json" --output "$preview_path" --format json --open
```

Use `--no-open` if the user wants the file or the browser is on another machine. Return the full rendered `markdown` in chat and share the generated preview. Fix validation errors in the source JSON and render again.

When the user wants to leave inline browser comments, use a persistent shell session and run this command instead. The local browser and CLI must be on the same machine.

```sh
visual-plan render "$plan_json" --output "$preview_path" --review
```

Share the Markdown plan streamed at startup and the review URL printed by the command. Tell the user to select a passage, save each comment, then choose **Submit feedback**. Keep the review session active while waiting. If you need to retrieve a submitted batch later, run `visual-plan feedback "$preview_path"` and select the submission for the plan and round under review.

## Revise after feedback

For every round of plan feedback, whether it arrives in chat or as submitted browser comments, open the current JSON and apply the feedback there. Use quoted text and step IDs to locate passages. Keep the plan ID and unaffected step IDs stable, and carry forward relevant detail from the current plan.

Run the renderer again to regenerate **both** the Markdown plan and the HTML preview from the revised JSON. Use the same preview path and keep any chosen rendering settings. Show the full revised Markdown in chat and share the updated preview. If comments came through chat while a review is still serving the old revision, stop that review session before opening the revision. When another round of inline comments is requested, start a fresh review session against the revised plan.
