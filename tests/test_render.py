import base64
import json
import re
from html import escape
from pathlib import Path

import pytest

from visual_plan import PlanError, load_plan, render_plan, validate_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def fixture(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def test_linear_preview_matches_markdown():
    plan = fixture("linear")
    rendered = render_plan(validate_plan(plan))
    assert '<ol class="sequence">' in rendered.html
    assert '<svg class="graph"' not in rendered.html
    for field in ("title", "goal"):
        assert plan[field] in rendered.markdown and plan[field] in rendered.html
    for number, step in enumerate(plan["steps"], start=1):
        assert f"### {number}. {step['title']}" in rendered.markdown
        for field in ("title", "detail", "outcome"):
            assert step[field] in rendered.markdown and step[field] in rendered.html
    assert rendered.html.index(plan["decisions"][0]["question"]) < rendered.html.index(plan["steps"][1]["outcome"])
    assert "## Open decisions" in rendered.markdown


def test_branching_preview_examples():
    plan = fixture("branching")
    rendered = render_plan(validate_plan(plan))
    markdown, html = rendered.markdown, rendered.html
    assert html.count('class="graph-edge"') == 7
    assert 'id="dependencies-arrow"' in html
    assert 'id="step-2-example-0-arrow"' in html
    assert '<label for="show-list">List</label>' in html
    assert 'class="step" id="step-' in html
    svg = base64.b64decode(re.search(r"data:image/svg\+xml;base64,([^\"]+)", html)[1]).decode("utf-8")
    for label in ("File size (MB)", "Latency (ms)", "Current exporter", "Streaming exporter"):
        assert label in svg and label in markdown
    assert "| Streaming exporter | 20 | 255 |" in markdown
    assert "<td>Streaming exporter</td><td>20</td><td>255</td>" in html
    assert '<th scope="col">Run count</th>' in html
    assert "| File size (MB) | Run count | Dataset |" in markdown
    assert "Running (worker) → Queued (queue) · retry" in markdown
    assert "Running (worker) → Queued (queue) · retry" in html
    literal = plan["steps"][2]["examples"][0]["text"]
    assert f"```csv\n{literal}```" in markdown
    assert f'<code class="language-csv">{literal}</code>' in html
    assert "<script src=" not in html


def test_bar_chart_categorical_with_named_series():
    plan = fixture("linear")
    plan["examples"] = [{
        "type": "plot", "caption": "Compare bands", "chart": "bar",
        "x_axis": {"label": "Band"}, "y_axis": {"label": "Count"},
        "series": [
            {"name": "_Baseline", "points": [{"x": "Small", "y": 10}, {"x": "Large", "y": 30}]},
            {"name": "Proposed", "points": [{"x": "Large", "y": 23}]},
        ],
    }]
    rendered = render_plan(validate_plan(plan))
    svg = base64.b64decode(re.search(r"data:image/svg\+xml;base64,([^\"]+)", rendered.html)[1]).decode()
    assert all(label in svg for label in ("Small", "Large", "_Baseline", "Proposed"))
    assert "| Proposed | Large | 23 |" in rendered.markdown


def test_order_and_escaping():
    plan = fixture("linear")
    plan["steps"].reverse()
    plan["title"] = "<img src=x onerror=alert(1)> [link](bad)"
    literal = "\r\n  <raw>&\n```\n  end  \n"
    plan["steps"][0]["examples"] = [
        {"type": "sample_output", "caption": "Literal", "text": literal},
        {"type": "table", "caption": "Cells", "columns": ["Column | value"], "rows": [["x\ny & <b> | z"]]},
    ]
    rendered = render_plan(validate_plan(plan))
    assert "### 1. Implement the download endpoint" in rendered.markdown
    assert "### 2. Define the export contract" in rendered.markdown
    assert plan["title"] not in rendered.html
    assert "&lt;img" in rendered.markdown
    assert r"\[link\]" in rendered.markdown
    assert f"````\n{literal}````" in rendered.markdown
    escaped_literal = escape(literal).replace("\r", "&#13;")
    assert f"<code>{escaped_literal}</code>" in rendered.html
    assert r"| x<br>y &amp; &lt;b&gt; \| z |" in rendered.markdown


@pytest.mark.parametrize(("change", "diagnostic"), [
    (lambda p: p.update(schema_version=2), r"schema_version: expected version 1"),
    (lambda p: p["steps"][1].update(id="contract"), r"steps\[1\]\.id .*duplicate step ID"),
    (lambda p: p["steps"][1].update(depends_on=["missing"]), r"steps\[1\]\.depends_on\[0\].*missing"),
    (lambda p: p["steps"][0].update(depends_on=["instrument"]), r"dependency cycle .*contract.*instrument"),
    (lambda p: p["decisions"][0].update(step_id="missing"), r"decisions\[0\]\.step_id: unknown step"),
    (lambda p: p["examples"][0]["series"][0]["points"][1].update(y=float("inf")), r"examples\[0\].*\.y: must be a finite number"),
    (lambda p: p["examples"][0]["series"][0]["points"][1].update(x="mixed"), r"examples\[0\].*\.x: plot x values"),
    (lambda p: p["steps"][0]["examples"][0]["rows"].append([10]), r"steps\[0\].examples\[0\].rows\[3\].*expected 3 cells"),
    (lambda p: p["steps"][1]["examples"][0]["edges"][0].update(to="missing"), r"steps\[1\].examples\[0\].edges\[0\].to .*unknown node"),
    (lambda p: p["steps"][2]["examples"][0].update(text=43), r"steps\[2\].examples\[0\].text .*not of type 'string'"),
    (lambda p: p["steps"][2]["examples"][0].update(language="md\n"), r"steps\[2\].examples\[0\].language"),
])
def test_invalid_plan_reports_location(change, diagnostic):
    plan = fixture("branching")
    change(plan)
    with pytest.raises(PlanError, match=diagnostic):
        validate_plan(plan)


def test_invalid_json_reports_line_and_column():
    with pytest.raises(PlanError, match="invalid JSON at line 2, column 1"):
        load_plan("{\ninvalid}")
