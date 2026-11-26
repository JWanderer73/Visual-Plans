"""Store browser review drafts and relay submitted feedback to the CLI."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock, Thread

from .render import review_html


def _database_path(preview: Path) -> Path:
    return preview.with_name(f"{preview.name}.feedback.sqlite3")


def _batch(row: sqlite3.Row) -> dict:
    return {
        "review_id": row["id"],
        "plan_id": row["plan_id"],
        "plan_title": row["plan_title"],
        "revision": row["revision"],
        "submitted_at": row["submitted_at"],
        "comments": json.loads(row["comments"]),
    }


def submitted_feedback(preview: Path) -> list[dict]:
    path = _database_path(preview)
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return [_batch(row) for row in db.execute(
            "SELECT * FROM reviews WHERE submitted_at IS NOT NULL ORDER BY submitted_at, id"
        )]


class _ReviewStore:
    def __init__(self, preview: Path, plan_id: str, plan_title: str, html: str):
        self.path = _database_path(preview)
        self.path.touch(mode=0o600, exist_ok=True)
        revision = sha256(html.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    plan_title TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    comments TEXT NOT NULL DEFAULT '[]',
                    submitted_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS current_draft ON reviews (plan_id, revision)
                WHERE submitted_at IS NULL;
            """)
            db.execute(
                "INSERT OR IGNORE INTO reviews (plan_id, plan_title, revision) VALUES (?, ?, ?)",
                (plan_id, plan_title, revision),
            )
            self.review_id = db.execute(
                "SELECT id FROM reviews WHERE plan_id = ? AND revision = ? AND submitted_at IS NULL",
                (plan_id, revision),
            ).fetchone()[0]

    def get(self) -> sqlite3.Row:
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM reviews WHERE id = ?", (self.review_id,)).fetchone()

    def save(self, version: int, comments: list[dict], submit: bool) -> bool:
        timestamp = datetime.now(timezone.utc).isoformat() if submit else None
        with closing(sqlite3.connect(self.path)) as db, db:
            updated = db.execute(
                """UPDATE reviews SET comments = ?, version = version + 1, submitted_at = ?
                   WHERE id = ? AND version = ? AND submitted_at IS NULL""",
                (json.dumps(comments, ensure_ascii=False), timestamp, self.review_id, version),
            )
            return updated.rowcount == 1


def _valid_comment(comment: object) -> bool:
    if not isinstance(comment, dict) or comment.keys() != {"id", "quote", "note", "start", "end", "step_ids"}:
        return False
    return (
        all(isinstance(comment[key], str) and comment[key].strip() for key in ("id", "quote", "note"))
        and type(comment["start"]) is int and type(comment["end"]) is int
        and 0 <= comment["start"] < comment["end"]
        and isinstance(comment["step_ids"], list)
        and all(isinstance(step_id, str) for step_id in comment["step_ids"])
    )


def _state(row: sqlite3.Row) -> dict:
    return {
        "version": row["version"],
        "comments": json.loads(row["comments"]),
        "submitted": row["submitted_at"] is not None,
    }


def _handler(store: _ReviewStore, html: str, path: str, origin: str, lock: Lock):
    document = review_html(html).encode("utf-8")
    endpoint = f"{path}feedback"
    host = origin.removeprefix("http://")

    class ReviewHandler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *_args):
            pass

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def do_GET(self):
            if self.headers.get("Host") != host:
                self.send_error(404)
            elif self.path == path:
                self._send(200, document, "text/html; charset=utf-8")
            elif self.path == endpoint:
                try:
                    self._json(200, _state(store.get()))
                except sqlite3.Error:
                    self._json(500, {"error": "Could not load saved feedback."})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.headers.get("Host") != host or self.path != endpoint:
                self.send_error(404)
                return
            if self.headers.get("Origin") != origin or self.headers.get_content_type() != "application/json":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    self._json(413, {"error": "This feedback exceeds the size limit."})
                    return
                data = json.loads(self.rfile.read(length))
                version, comments, submit = data["version"], data["comments"], data["submit"]
                if (
                    type(version) is not int or not 0 <= version < 2**63 - 1 or type(submit) is not bool
                    or not isinstance(comments, list) or not all(map(_valid_comment, comments))
                    or len({comment["id"] for comment in comments}) != len(comments)
                    or (submit and not comments)
                ):
                    raise ValueError("invalid feedback")
                # Reject lone surrogates before encoding the draft in SQLite.
                json.dumps(comments, ensure_ascii=False).encode("utf-8")
            except (ValueError, KeyError, TypeError, RecursionError):
                self._json(400, {"error": "Invalid feedback."})
                return
            try:
                with lock:
                    saved = store.save(version, comments, submit)
                    self._json(200 if saved else 409, _state(store.get()))
            except sqlite3.Error:
                self._json(500, {"error": "Could not save feedback. Try again."})

    return ReviewHandler


def collect_feedback(preview: Path, plan_id: str, plan_title: str, html: str, ready) -> dict:
    """Serve this preview on loopback until the reviewer submits the draft."""
    store = _ReviewStore(preview, plan_id, plan_title, html)
    path = f"/{token_urlsafe(24)}/"
    lock = Lock()
    with ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        server.RequestHandlerClass = _handler(store, html, path, origin, lock)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            ready(origin + path)
            while True:
                # Other instances reviewing the same draft can submit it too.
                with lock:
                    row = store.get()
                if row["submitted_at"] is not None:
                    return _batch(row)
                thread.join(timeout=0.5)
        finally:
            server.shutdown()
            thread.join()
