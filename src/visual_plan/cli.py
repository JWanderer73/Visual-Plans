"""Read plans, save previews atomically, and report results to callers."""

import argparse
import json
import subprocess
import sys
import tomllib
import webbrowser
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from platformdirs import user_cache_path, user_config_path

from .render import LAYOUTS, THEMES, render_plan
from .validation import load_plan

APP_NAME = "visual-plan"


@dataclass(frozen=True)
class Settings:
    theme: str = "system"
    layout: str = "auto"
    open_browser: bool = False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Render a plan for chat and browser review.")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="render a JSON plan")
    source = render.add_mutually_exclusive_group(required=True)
    source.add_argument("plan", nargs="?", type=Path, help="JSON plan file")
    source.add_argument("--stdin", action="store_true", help="read a JSON plan from standard input")
    render.add_argument("--format", choices=("markdown", "json"), default="markdown", help="standard output format")
    render.add_argument("--output", type=Path, metavar="PATH", help="write the HTML preview to this path")
    render.add_argument("--config", type=Path, metavar="PATH", help="read settings from this TOML file")
    render.add_argument("--theme", choices=THEMES, help="override the saved preview theme")
    render.add_argument("--layout", choices=LAYOUTS, help="override the saved overview layout")
    render.add_argument(
        "--open", action=argparse.BooleanOptionalAction, default=None, dest="open_browser",
        help="open the written preview in a browser",
    )
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    path = args.config or user_config_path(APP_NAME, appauthor=False) / "config.toml"
    try:
        with path.expanduser().open("rb") as config:
            saved = tomllib.load(config)
    except FileNotFoundError:
        if args.config is not None:
            raise
        saved = {}
    except (ValueError, OSError) as error:
        raise ValueError(f"{path}: {error}") from error

    defaults = Settings()
    unknown = saved.keys() - {"theme", "layout", "open_browser"}
    if unknown:
        raise ValueError(f"{path}: unknown setting {min(unknown)!r}")
    theme = saved.get("theme", defaults.theme)
    layout = saved.get("layout", defaults.layout)
    open_browser = saved.get("open_browser", defaults.open_browser)
    if theme not in THEMES:
        raise ValueError(f"{path}: theme must be one of {', '.join(THEMES)}")
    if layout not in LAYOUTS:
        raise ValueError(f"{path}: layout must be one of {', '.join(LAYOUTS)}")
    if not isinstance(open_browser, bool):
        raise ValueError(f"{path}: open_browser must be true or false")
    return Settings(
        theme=args.theme if args.theme is not None else theme,
        layout=args.layout if args.layout is not None else layout,
        open_browser=args.open_browser if args.open_browser is not None else open_browser,
    )


def _project_root(cwd: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return cwd.resolve()
    if result.returncode == 0 and result.stdout:
        return Path(result.stdout.rstrip(b"\n\r").decode(sys.getfilesystemencoding(), errors="surrogateescape")).resolve()
    return cwd.resolve()


def _preview_path(output: Path | None, plan_id: str) -> Path:
    if output is not None:
        return output.expanduser().resolve()
    project = str(_project_root(Path.cwd()))
    project_key = sha256(project.encode("utf-8", errors="surrogatepass")).hexdigest()
    plan_key = sha256(plan_id.encode("utf-8")).hexdigest()
    return (user_cache_path(APP_NAME, appauthor=False) / project_key / f"{plan_key}.html").resolve()


def _write_preview(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=".visual-plan-", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(html)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _open_preview(path: Path) -> str:
    try:
        if webbrowser.open(path.as_uri(), new=2):
            return "opened"
        reason = "no browser reported a successful launch"
    except (OSError, webbrowser.Error) as error:
        reason = str(error)
    print(f"{APP_NAME}: could not open the browser: {reason}", file=sys.stderr)
    return "failed"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.stdin:
            source = sys.stdin.buffer.read().decode("utf-8-sig")
        else:
            source = args.plan.expanduser().read_text(encoding="utf-8-sig")
        plan = load_plan(source)
        settings = _settings(args)
        rendered = render_plan(plan, theme=settings.theme, layout=settings.layout)
        path = _preview_path(args.output, plan["id"])
        _write_preview(path, rendered.html)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"{APP_NAME}: {error}", file=sys.stderr)
        return 1

    open_status = _open_preview(path) if settings.open_browser else "not_requested"
    if args.format == "json":
        print(json.dumps({
            "markdown": rendered.markdown,
            "preview_path": str(path),
            "open_status": open_status,
        }, ensure_ascii=False))
    else:
        sys.stdout.write(rendered.markdown)
        print(path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
