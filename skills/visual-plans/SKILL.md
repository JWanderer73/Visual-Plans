---
name: visual-plans
description: Use whenever the user asks to create or revise a plan, including “make a plan” and “plan this out.” Save the plan document and open its matching browser review. Include a visual mockup for planned reports. Also use for browser review and feedback on an existing plan.
---

# Visual Plans

The saved Markdown document is the official plan. Agents use it for implementation and handoffs. The visual plan is solely for human review and feedback.

## Draft the plan

Inspect the context relevant to the request, including the target repository when planning code changes. Keep the detail proportional to the task and include relevant design choices, constraints, tradeoffs, tests, and open decisions. Use these prompts to fill gaps in the plan where they matter.

- **Inputs** — Identify what the planned code will consume. Name the datasets, files, APIs, configuration, or user inputs and describe the fields, formats, versions, or assumptions that affect the work. Mark unconfirmed sources as open decisions when the choice matters.
- **Execution order** — Identify the entry point and the files, scripts, jobs, or stages that run. Show their order and what they pass downstream. Distinguish execution order from implementation order when they differ. Describe parallel branches, joins, or conditional paths where they affect the pipeline. For work with a single entry point, describe its actual execution flow.
- **Outputs** — Describe what the work will produce and where it will go. Give expected file paths, formats, table columns, plot axes, API responses, or other acceptance details when relevant. Include a small sample table, plot, diagram, or literal output when it helps the reviewer understand the deliverable. Label illustrative values as sample data.

Use the prompts within the appropriate steps and omit details with no bearing on the task. A plan for a small UI fix can describe its behavior and verification without a dataset or a multi-file pipeline.

## Render and review

Use the [Visual Plan v1 schema](references/plan-v1.schema.json). Write a single JSON plan with a stable plan ID and step IDs. Put implementation details and outcomes in the steps, use `depends_on` for actual prerequisites, and attach examples and unresolved questions to the work they affect. Place a deliverable example at plan level when it describes the overall result.

### Show the proposed report

Whenever a deliverable is a report, populate the plan-level `examples` array with a representative excerpt of the finished report on the first draft. Arrange the examples in report reading order, with the proposed section titles in their captions. Render the actual chart types, units, series, comparisons, and table columns the reader will see. For a prose report, include a sample headline and passage using `sample_output`. Use real values when established, or label illustrative figures and findings as sample data in the visible captions. A step that promises to produce a chart still needs the chart mockup. Revise the examples whenever feedback changes the proposed report.

## Save the document and open the review

Use stable paths for the source JSON, Markdown plan document, and HTML preview. Update the existing plan document at its original path. Before each revision, reconcile the rendering JSON with the current Markdown so direct edits to the official plan survive regeneration. For a new plan, save the Markdown alongside the JSON. Keep the Markdown complete enough to execute on its own. In chat or terminal replies, give only a brief change summary and links to the live browser review and saved document.

For every draft and revision, render the document and preview from the same JSON. Stage the Markdown beside the destination so a failed render preserves the previous document. Run these commands from the target repository with the three paths set:

```sh
(
  set -e
  draft=$(mktemp "${plan_doc}.XXXXXX")
  trap 'rm -f "$draft"' EXIT
  visual-plan render "$plan_json" --output "$preview_path" --no-open > "$draft"
  mv "$draft" "$plan_doc"
)
```

On success, start the live review in a persistent shell session with a short initial yield so you receive the review URL while the command is running. Keep its session handle. Use the same rendering options as the first render. Capture JSON stdout in a private temporary file unique to this invocation. The CLI prints the live URL and errors to stderr and writes the result on submission.

```sh
review_result=$(mktemp) || exit 1
printf 'Review result file: %s\n' "$review_result" >&2
visual-plan render "$plan_json" --output "$preview_path" --review --format json > "$review_result"
```

Send the URL printed after `Review:` and the document link immediately in a progress message. Keep the agent turn active and wait on that shell session (in Codex, poll with `write_stdin`, empty input, and waits of up to 60 seconds). A timeout means the review is still open. Continue waiting quietly. If the user gives feedback in chat, handle it immediately. If they finish or cancel the review, stop waiting and close the session.

When the command exits successfully, read only the `feedback` field from its result file. It contains the exact submitted batch for this invocation. Apply it immediately using the revision workflow below, share the updated links in a progress message, and wait on the new review in the same way. Submission is the user's request to revise the plan and needs no follow-up chat message. If the command fails, inspect stderr and recover the review; a failure is not a submission.

If the user requests an offline file or the browser cannot reach the server, share the static HTML from the first render. Fix validation errors and retry before reporting an update.

## Revise after feedback

Treat feedback in ordinary chat as a request to edit the current plan immediately, just like submitted browser comments. Apply it to the source JSON, including any affected examples. Keep the plan ID, unaffected step IDs, and existing paths stable. Regenerate the document and preview, then replace the prior live review with a fresh one serving the revision. Verify the requested change appears in both saved artifacts. For reports, check the rendered HTML contains the proposed figures, tables, or sample passages. Reply with the links and a short summary of what changed.
