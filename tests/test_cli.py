import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from visual_plan import cli

LINEAR = Path(__file__).resolve().parents[1] / "examples" / "linear.json"


@pytest.fixture(autouse=True)
def user_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "user_cache_path", lambda *args, **kwargs: tmp_path / "cache")
    monkeypatch.setattr(cli, "user_config_path", lambda *args, **kwargs: tmp_path / "config")


def test_plain_output(tmp_path, capsys):
    output = tmp_path / "review folder" / "plan.html"
    assert cli.main(["render", str(LINEAR), "--output", str(output)]) == 0
    streams = capsys.readouterr()
    assert streams.out.startswith("# Add account data export\n")
    assert streams.err == f"{output}\n"
    assert output.is_file()


def test_stdin_emits_one_json_object(tmp_path):
    output = tmp_path / "plan.html"
    result = subprocess.run(
        [sys.executable, "-m", "visual_plan.cli", "render", "--stdin",
         "--format", "json", "--output", str(output), "--no-open"],
        input=LINEAR.read_text(encoding="utf-8"), capture_output=True, check=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert payload.keys() == {"markdown", "preview_path", "open_status"}
    assert payload["markdown"].startswith("# Add account data export")
    assert payload["preview_path"] == str(output)
    assert payload["open_status"] == "not_requested"
    assert result.stderr == ""


def test_open_failure_leaves_preview_and_stdout_usable(monkeypatch, tmp_path, capsys):
    output = tmp_path / "a space" / "plan.html"

    def open_preview(uri, *, new):
        assert uri == output.as_uri()
        assert new == 2
        assert output.is_file()
        raise OSError("browser unavailable")

    monkeypatch.setattr(cli.webbrowser, "open", open_preview)
    assert cli.main(["render", str(LINEAR), "--format", "json", "--output", str(output), "--open"]) == 0
    streams = capsys.readouterr()
    payload = json.loads(streams.out)
    assert payload["open_status"] == "failed"
    assert payload["preview_path"] == str(output)
    assert "browser unavailable" in streams.err


def test_cli_flags_override_saved_preferences(monkeypatch, tmp_path, capsys):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text('theme = "dark"\nlayout = "list"\nopen_browser = true\n')
    output = tmp_path / "plan.html"
    opens = []

    def open_preview(uri, *, new):
        opens.append(uri)
        return True

    monkeypatch.setattr(cli.webbrowser, "open", open_preview)
    args = ["render", str(LINEAR), "--format", "json", "--output", str(output)]
    assert cli.main(args) == 0
    html = output.read_text()
    assert 'data-theme="dark"' in html
    assert '<ol class="sequence">' not in html
    assert json.loads(capsys.readouterr().out)["open_status"] == "opened"
    assert cli.main([*args, "--theme", "light", "--layout", "diagram", "--no-open"]) == 0
    html = output.read_text()
    assert 'data-theme="light"' in html
    assert '<svg class="graph"' in html
    assert json.loads(capsys.readouterr().out)["open_status"] == "not_requested"
    assert opens == [output.as_uri()]


def test_cache_uses_git_root_and_distinguishes_projects(monkeypatch, tmp_path):
    if shutil.which("git") is None:
        pytest.skip("Git is needed for repository-root detection")
    parent = tmp_path / "repo"
    child = parent / "subfolder"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(parent)], check=True)
    monkeypatch.chdir(parent)
    first = cli._preview_path(None, "../../same-plan/")
    monkeypatch.chdir(child)
    assert cli._preview_path(None, "../../same-plan/") == first
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    second = cli._preview_path(None, "../../same-plan/")
    assert second.parent != first.parent
    assert second.name == first.name
    assert second.is_relative_to(tmp_path / "cache")


def test_revision_and_invalid_revision_use_same_preview(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "plan.json"
    plan = json.loads(LINEAR.read_text())
    source.write_text(json.dumps(plan))
    args = ["render", str(source), "--format", "json"]
    assert cli.main(args) == 0
    preview = Path(json.loads(capsys.readouterr().out)["preview_path"])
    first = preview.read_text()
    plan["title"] = "A revised plan"
    source.write_text(json.dumps(plan))
    assert cli.main(args) == 0
    assert Path(json.loads(capsys.readouterr().out)["preview_path"]) == preview
    revised = preview.read_text()
    assert "A revised plan" in revised and revised != first
    plan["steps"][0]["depends_on"] = ["endpoint"]
    source.write_text(json.dumps(plan))
    assert cli.main(args) == 1
    streams = capsys.readouterr()
    assert streams.out == ""
    assert "dependency cycle" in streams.err
    assert preview.read_text() == revised
    assert list(preview.parent.iterdir()) == [preview]


def test_atomic_write_cleans_temp_file_on_replace_failure(monkeypatch, tmp_path):
    output = tmp_path / "plan.html"
    output.write_text("previous")

    def fail_replace(source, target):
        assert source.parent == target.parent
        assert source.read_text() == "updated"
        assert target.read_text() == "previous"
        raise PermissionError("cannot replace")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError):
        cli._write_preview(output, "updated")
    assert output.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [output]
