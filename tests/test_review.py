import json
from pathlib import Path

from visual_plan import cli
from visual_plan.review import _ReviewStore, submitted_feedback

LINEAR = Path(__file__).resolve().parents[1] / "examples" / "linear.json"


def test_review_draft_is_resumable_and_submissions_survive_new_revisions(tmp_path):
    preview = tmp_path / "plan.html"
    comments = [{
        "id": "comment-1", "quote": "fields", "note": "List the exact fields.",
        "start": 18, "end": 24, "step_ids": ["contract"],
    }]
    assert submitted_feedback(preview) == []
    draft = _ReviewStore(preview, "account-export", "Export", "first revision")
    assert draft.save(0, comments, submit=False)
    assert submitted_feedback(preview) == []

    resumed = _ReviewStore(preview, "account-export", "Export", "first revision")
    assert resumed.review_id == draft.review_id
    assert json.loads(resumed.get()["comments"]) == comments
    assert not resumed.save(0, [], submit=False)
    assert resumed.save(1, comments, submit=True)
    assert not draft.save(2, [], submit=False)

    revised = _ReviewStore(preview, "account-export", "Export", "second revision")
    repeated = _ReviewStore(preview, "account-export", "Export", "first revision")
    assert json.loads(revised.get()["comments"]) == json.loads(repeated.get()["comments"]) == []
    [batch] = submitted_feedback(preview)
    assert batch["review_id"] == draft.review_id
    assert batch["plan_id"] == "account-export"
    assert batch["comments"] == comments


def test_review_returns_feedback_in_json_and_exposes_it_later(monkeypatch, tmp_path, capsys):
    output = tmp_path / "plan.html"
    url = "http://127.0.0.1:45321/session/"
    launches = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda address, **kwargs: launches.append(address) or True)

    def finish_review(preview, plan_id, title, html, ready):
        assert preview == output
        assert html == preview.read_text(encoding="utf-8")
        ready(url)
        store = _ReviewStore(preview, plan_id, title, html)
        comments = [{
            "id": "comment-1", "quote": "fields", "note": "Include field types.",
            "start": 18, "end": 24, "step_ids": ["contract"],
        }]
        assert store.save(0, comments, submit=True)
        return submitted_feedback(preview)[0]

    monkeypatch.setattr(cli, "collect_feedback", finish_review)
    assert cli.main(["render", str(LINEAR), "--output", str(output), "--review", "--format", "json"]) == 0
    streams = capsys.readouterr()
    payload = json.loads(streams.out)
    assert payload["preview_path"] == str(output)
    assert payload["open_status"] == "opened"
    assert payload["feedback"]["comments"][0]["note"] == "Include field types."
    assert streams.err.splitlines() == [str(output), f"Review: {url}"]
    assert launches == [url]

    assert cli.main(["feedback", str(output)]) == 0
    assert json.loads(capsys.readouterr().out) == [payload["feedback"]]
